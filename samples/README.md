# Sample Data

## `sydney_cbd_dev.kismetdb`

Synthetic Kismet-style SQLite database for local development around Sydney CBD.

- 8 devices
- 120 valid GPS packet observations
- Approximate path from Town Hall through Wynyard, Circular Quay, and Haymarket
- Includes a few invalid rows with missing GPS or zero signal so backend filtering can be tested

Use it from the file picker after starting the app:

```bash
./run.sh
```

Then browse to:

```text
samples/sydney_cbd_dev.kismetdb
```

The data is synthetic and does not represent real access points or real captures.
