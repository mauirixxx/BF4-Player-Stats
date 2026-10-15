/* BF4PS lightweight homepage data adapter. Feature branch; not loaded in production. */
(function (root) {
  'use strict';
  const METRICS = new Set(['kills','total_score','wins','time_played_seconds','conquest_score','rush_score','team_deathmatch_score','domination_score','obliteration_score','defuse_score','capture_the_flag_score','air_superiority_score','carrier_assault_score','chain_link_score']);
  const PLATFORMS = new Set(['all','pc','ps4','xboxone']);
  const REQUEST_TIMEOUT_MS = 8000;
  async function json(url, fetcher = fetch) {
    const response = await fetcher(url, {cache:'no-store',signal:AbortSignal.timeout(REQUEST_TIMEOUT_MS)});
    if (!response.ok) throw new Error('BF4PS data HTTP ' + response.status);
    return response.json();
  }
  function generalUrl({metric='kills',platform='all',page=1,pageSize=50,search='',division=0}={}) {
    if (!METRICS.has(metric) || !PLATFORMS.has(platform)) throw new Error('Unsupported metric or platform');
    if (!Number.isSafeInteger(page) || page<1 || !Number.isSafeInteger(pageSize) || pageSize<1 || pageSize>100) throw new Error('Invalid pagination');
    if (!Number.isSafeInteger(division) || division<0 || division>10) throw new Error('Invalid division');
    const q = new URLSearchParams({metric,platform,page:String(page),page_size:String(pageSize),search:String(search).slice(0,100),division:String(division)});
    return '/bf4ps-api/general-leaderboard?' + q;
  }
  function searchUrl(query) {
    const term = String(query).trim();
    return term.length >= 2 ? '/bf4ps-api/global-soldier-search?q=' + encodeURIComponent(term.slice(0,80)) : null;
  }
  async function summary(fetcher) {
    const result = await json('/homepage-summary.json?t=' + Date.now(),fetcher);
    if (!result || !result.summary || !Number.isFinite(result.detailed_soldiers) || !Number.isFinite(result.full_soldiers)) throw new Error('Invalid homepage summary');
    return result;
  }
  async function general(options,fetcher) {
    const result = await json(generalUrl(options),fetcher);
    if (!Array.isArray(result.rows) || !Number.isSafeInteger(result.population) || !Number.isSafeInteger(result.filtered_count)) throw new Error('Invalid leaderboard response');
    return result;
  }
  async function search(query,fetcher) {
    const url=searchUrl(query);
    if (!url) return {rows:[]};
    const result=await json(url,fetcher);
    if (!Array.isArray(result.rows)) throw new Error('Invalid search response');
    return result;
  }
  root.BF4PSPaginated={summary,general,search,generalUrl,searchUrl};
})(typeof window !== 'undefined' ? window : globalThis);
