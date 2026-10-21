# BF4PS Phase 3D two-host network preflight

Status: **validated Phase 3D prerequisite evidence**

This record preserves the network/database prerequisites proven before deploying the Phase 3D two-host distributed collector harness. It supplements the frozen `docs/phase3-distributed-collector-design.md`; it does not change that design.

## Frozen initial hosts

The first Phase 3D distributed proof uses:

| Site | Host | LAN address | Public IPv4 egress |
|---|---|---:|---:|
| Honolulu | `hnl-01` | `192.168.5.70` | `76.81.69.106` |
| Kahului | `kah-01` | `192.168.21.70` | `98.155.184.38` |

The two hosts therefore have distinct real Internet egress IPs. Per the frozen Phase 3 design, they must use distinct BF4PS `egress_key` values during the two-host proof. The egress key models the real external rate-limit domain; it is not merely a collector name.

## Database endpoint rule: use FQDNs

BF4PS distributed hosts must use the database FQDN:

`mak-db-02.bf4statusbot.com`

For this environment, do **not** depend on the short hostname `mak-db-02`.

Live preflight showed that `mak-db-02` did not resolve on either `hnl-01` or `kah-01`, while `mak-db-02.bf4statusbot.com` resolved correctly to `192.168.10.78` on both hosts.

This is an operational rule for BF4PS deployment/configuration: cross-site infrastructure references should use the working FQDN rather than assuming a DNS search suffix is configured on every worker.

## Routing and PostgreSQL reachability

Both remote hosts successfully routed to `192.168.10.78` through their local site gateways and reached PostgreSQL TCP/5432 at `mak-db-02.bf4statusbot.com`.

Initial `pg_isready` checks established TCP reachability before database authentication was enabled.

## PostgreSQL HBA prerequisite

The existing BF4PS test migrator rule allowed only the `tcou` host (`192.168.10.71/32`). The first authenticated remote connection therefore correctly failed with `no pg_hba.conf entry`.

Two narrow `/32` rules were added to `/etc/postgresql/16/main/pg_hba.conf` for the Phase 3D hosts:

```text
host    bf4_playerstats_test    bf4_playerstats_test_migrator    192.168.5.70/32     scram-sha-256
host    bf4_playerstats_test    bf4_playerstats_test_migrator    192.168.21.70/32    scram-sha-256
```

The existing `tcou` rule remains:

```text
host    bf4_playerstats_test    bf4_playerstats_test_migrator    192.168.10.71/32    scram-sha-256
```

`pg_hba_file_rules` reported no parse errors and showed all three BF4PS rules using `scram-sha-256`.

The narrow `/32` scope is deliberate for the current test migrator role. Whole-site `/24` access is not required for this Phase 3D proof.

## Authenticated database validation

After the HBA change became active, authenticated read-only validation succeeded independently from both `hnl-01` and `kah-01`.

Both hosts confirmed:

- database: `bf4_playerstats_test`;
- authenticated role: `bf4_playerstats_test_migrator`;
- server address: `192.168.10.78`;
- server port: `5432`;
- `pg_is_in_recovery() = false`;
- Alembic revision: `0003_request_gates`.

Therefore both remote hosts are proven to reach the same writable BF4PS test PostgreSQL database required by Phase 3D.

## PostgreSQL service-management observation

On `mak-db-02`, the generic Debian/Ubuntu `postgresql.service` unit was inactive and could not be used as the reload target even though the PostgreSQL cluster itself was reachable and serving queries. Future operational work must identify/use the actual running PostgreSQL cluster/unit (or an appropriate PostgreSQL reload mechanism) rather than assuming the generic meta-unit is active.

The successful authenticated remote connections after the HBA update are the functional proof that the required HBA rules were active for this test.

## Credential boundary

The current network proof used `bf4_playerstats_test_migrator` because it is the existing BF4PS test-database credential.

This does **not** establish the migrator as the desired long-running production collector role. Before production collector credentials/grants are introduced, privileges must be derived from the canonical schema, current Alembic migrations, and actual collector persistence paths rather than guessed.

## Phase 3D network/database prerequisite result

**PASS**

`hnl-01` and `kah-01` have:

- working FQDN resolution to the selected BF4PS test database endpoint;
- working cross-site routing;
- working PostgreSQL TCP reachability;
- explicit HBA authorization;
- successful authenticated access to the same writable test database;
- confirmed Alembic head `0003_request_gates`;
- distinct public Internet egress IPs suitable for distinct request-gate domains.

The next Phase 3D step is to prepare an isolated BF4PS runtime on both hosts, perform a no-Battlelog deployment/preflight, freeze the distributed test cohort and collector identities, and only then execute a bounded two-host live collection proof.
