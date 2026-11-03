"""Opt-in compact snapshot reader. Call inside REPEATABLE READ READ ONLY.

Return None for missing/stale scope, preserving the existing leaderboard path.
This first candidate uses bounded blocks but still scans the compact generation
for unfiltered division counts; optimize before enabling production globally.
"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import text
from bf4ps.compact_rank_codec import decode_block

CUTOFFS = (3, 8, 15, 25, 35, 50, 65, 80, 90)


def get_compact_page(conn, kind, platform, item, page, page_size, search, division, metric):
    if kind not in ('weapon', 'vehicle') or platform not in ('pc', 'ps4', 'xboxone', 'all'):
        return None
    if metric not in (('kills', 'kpm', 'accuracy') if kind == 'weapon' else ('kills', 'kpm')):
        return None
    if item < 1 or page < 1 or not 1 <= page_size <= 100 or division not in range(11):
        return None
    params = {'kind':kind,'platform':platform,'item':item,'metric':metric}
    published = conn.execute(text('''SELECT g.generation_id,g.row_count,g.completed_at
      FROM equipment_rank_compact_published p
      JOIN equipment_rank_generations g ON g.generation_id=p.generation_id
      WHERE p.kind=:kind AND p.item_id=:item AND p.platform=:platform AND p.metric=:metric
      AND g.status='published' AND g.snapshot_format=1 AND g.input_scope_version IS NOT NULL
      AND g.completed_at >= now() - interval '72 hours'
      AND g.input_scope_version=(SELECT v.version FROM equipment_rank_scope_versions v
        WHERE v.kind=p.kind AND v.item_id=p.item_id AND v.platform=p.platform) '''), params).mappings().first()
    if published is None:
        return None
    generation = published['generation_id']
    population = int(published['row_count'])
    if population <= 0:
        return None
    excluded = conn.execute(text('''SELECT 1 FROM equipment_rank_compact_lookup l
      JOIN soldiers s ON s.soldier_id=l.soldier_id
      JOIN player_exclusions x ON x.platform=s.platform AND x.persona_id=s.persona_id AND x.active
      WHERE l.generation_id=:g LIMIT 1'''),{'g':generation}).first()
    if excluded is not None:
        return None
    search = (search or '').lower()
    selected = None
    if search:
        # Name/persona filtering is performed by the existing indexed identity
        # table, then intersected with the immutable generation lookup.
        hits = conn.execute(text('''SELECT l.soldier_id FROM equipment_rank_compact_lookup l
          JOIN soldiers s ON s.soldier_id=l.soldier_id
          WHERE l.generation_id=:g AND
          (lower(s.current_name) LIKE :pattern OR s.persona_id::text LIKE :pattern)'''),
          {'g':generation,'pattern':'%'+search+'%'}).scalars().all()
        selected = set(hits)
        if not selected:
            return {'population':population,'filtered_count':0,'page':page,'page_size':page_size,
                    'total_pages':0,'rows':[],'rank_updated_at':published['completed_at']}
    offset = (page-1)*page_size
    # Ordinary pages need only the compressed blocks intersecting their page.
    # The exclusion join above still guards every soldier in format-1 snapshots.
    ordinary_page = not search and division == 0
    if ordinary_page:
        blocks = conn.execute(text('''SELECT block_id,first_position,last_position,payload
          FROM equipment_rank_compact_blocks WHERE generation_id=:g
            AND last_position >= :first AND first_position <= :last
          ORDER BY block_id'''),
          {'g':generation,'first':offset+1,'last':offset+page_size}).mappings()
    else:
        blocks = conn.execute(text('''SELECT block_id,first_position,last_position,payload
          FROM equipment_rank_compact_blocks WHERE generation_id=:g ORDER BY block_id'''),
          {'g':generation}).mappings()
    count = 0
    page_rows = []
    for block in blocks:
        decoded = decode_block(bytes(block['payload']))
        if len(decoded) != block['last_position'] - block['first_position'] + 1:
            raise ValueError('compact snapshot block size mismatch')
        for index, values in enumerate(decoded):
            soldier, rank, kills, kpm, accuracy, fetched = values
            if selected is not None and soldier not in selected:
                continue
            top_pct = rank * 100.0 / population
            band = next((i for i,cutoff in enumerate(CUTOFFS,1) if top_pct <= cutoff),10)
            if division and division != band:
                continue
            position_index = block['first_position'] + index - 1 if ordinary_page else count
            if offset <= position_index < offset + page_size:
                page_rows.append({'soldier_id':soldier,'rank':rank,
                                  'position':block['first_position']+index,
                                  'kills':kills,'kpm':None if kpm is None else Decimal(kpm),
                                  'accuracy':None if accuracy is None else Decimal(accuracy),
                                  'source_fetched_at':None if fetched is None else datetime.fromisoformat(fetched),
                                  'top_pct':top_pct,'division':band})
            count += 1
    if ordinary_page:
        count = population
        if offset < population and len(page_rows) != min(page_size, population-offset):
            raise ValueError('compact snapshot page has missing rows')
    if page_rows:
        ids = [row['soldier_id'] for row in page_rows]
        identities = {r['soldier_id']:r for r in conn.execute(text('''SELECT soldier_id,current_name,persona_id,platform
          FROM soldiers WHERE soldier_id=ANY(:ids)'''),{'ids':ids}).mappings()}
        if len(identities) != len(page_rows):
            raise ValueError('compact snapshot references missing soldier identities')
        for row in page_rows:
            row.update(identities[row['soldier_id']])
    return {'population':population,'filtered_count':count,'page':page,'page_size':page_size,
            'total_pages':(count+page_size-1)//page_size,'rows':page_rows,
            'rank_updated_at':published['completed_at']}

[executed on device: rnt-01 (aa6d9aec-0414-4ad7-b824-1d53cc1368b2)]