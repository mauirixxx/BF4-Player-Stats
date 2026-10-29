# Battle Reports V1 schema

Approved logical model: servers, battle_reports, players, report_players, player_name_history. No migration deployed. Persona ID and platform are identity keys; report participation preserves the name observed at collection, not historical round name. Player-name changes and reversions are retained. Future BF4PS import is one-way, deduplicated and admission-policy-aware. No per-round statistics.
