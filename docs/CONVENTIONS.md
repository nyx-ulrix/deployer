# Database Planning Conventions

The schema viewer draws every project's databases as an **entity-relationship diagram (ERD) using
crow's-foot notation**, and checks each schema against the conventions below. Violations are shown
as warnings in the viewer's *Conventions* panel (they never block anything).

## Diagram notation

| Symbol | Meaning |
|---|---|
| Entity box header | Table (SQL) or collection (NoSQL); badge shows engine + data source name |
| `PK` | Primary key (`_id` for MongoDB) |
| `FK` | Foreign key (declared constraint) |
| `UQ` | Unique constraint / unique index |
| `NN` | Not null |
| `IDX` | Indexed (non-unique) |
| `?` after a Mongo field | Field present in fewer than 100% of sampled documents |
| Solid line | Declared relationship (SQL foreign key) |
| Dashed line | Inferred relationship (naming convention / Mongo reference) |
| Dotted line, different colour | **Cross-database link** (SQL ↔ NoSQL), declared by a user |
| Line ends | `|│` exactly one · `o│` zero or one · `│<` one or many · `o<` zero or many |

## Naming

| ID | Rule | Severity |
|---|---|---|
| N1 | Table / collection names are `snake_case` | warning |
| N2 | Table / collection names are plural (`users`, `order_items`) | info |
| N3 | Column / field names are `snake_case` (Mongo `_id` exempt) | warning |
| N4 | No SQL reserved words as table or column names | warning |
| N5 | Foreign-key columns are named `<singular_referenced_table>_id` (`user_id` → `users.id`) | info |
| N6 | Boolean columns start with `is_` / `has_` / `can_` | info |

## Structure

| ID | Rule | Severity |
|---|---|---|
| S1 | Every SQL table has a primary key | warning |
| S2 | Single-column primary key is named `id` | info |
| S3 | Every foreign-key column is indexed | warning |
| S4 | Columns named `*_id` that match a table have a declared FK constraint (SQL) or an index (Mongo) | info |
| S5 | Tables have `created_at` and `updated_at` timestamps | info |
| S6 | Primary-key columns are not nullable | warning |
| S7 | Mongo field has one consistent type across sampled documents | warning |
| S8 | Mongo collections that are queried by a reference field have an index on it | info |

## Cross-database links

| ID | Rule | Severity |
|---|---|---|
| X1 | Both ends of a link exist in the current schema | warning |
| X2 | Linked field types are compatible (e.g. `BIGINT` ↔ `int`/`long`, `CHAR(36)` ↔ `string`) | warning |
| X3 | The "many" side of a link is indexed | info |

## DDL export

- **SQL** — `CREATE TABLE` statements in foreign-key dependency order, followed by indexes, wrapped
  with `SET FOREIGN_KEY_CHECKS=0/1` for MariaDB/MySQL. Uses the server's own `SHOW CREATE TABLE`
  for MariaDB/MySQL and SQLAlchemy's dialect compiler for PostgreSQL.
- **MongoDB** — a `mongosh` script: `db.getSiblingDB(...)`, `db.createCollection(name, {validator})`
  (existing `$jsonSchema` validators kept; otherwise a validator inferred from samples is emitted
  commented-out), then `createIndex` for every non-`_id` index.
- **Bundle** — a `.zip` with `schema.sql`, `schema.mongo.js`, `links.json` (cross-database links)
  and a `README.md` explaining the order to run them.
