# PDF Generator Sandbox

Minimal isolated renderer image used on demand by the dispatcher for larger certificate jobs. This image is built by Compose but is not itself a long-running Compose service; the dispatcher's container pool creates and removes sandbox containers as needed.

## Runtime behavior

- `generate.py` reads the mounted job input, renders one PDF per valid recipient, and writes files beneath `/output`.
- Recipient-level errors are reported independently; a failed recipient does not abort the remaining batch.
- The generator updates recipient/job data using the configured database connection.
- Dispatcher limits sandbox memory, CPU, PIDs, network, runtime, and container lifetime. The shared storage volume connects sandbox output to the API download service.

## Build and inspect

From the repository root:

```powershell
docker compose build pdf-generator
```

The `pdf-generator` service's Compose command is only an image-build placeholder. Do not start it as the application worker; the dispatcher owns sandbox lifecycle.

## Configuration

The dispatcher supplies the job, database and storage configuration when it starts a sandbox. Image dependencies are pinned in `requirements.txt`; the container entry point remains idle until the dispatcher executes the generator.

## Tests

PDF output and sandbox behavior are tested from `../tests/test_certificate_pdf.py` and `../tests/test_threshold_switching.py`.
