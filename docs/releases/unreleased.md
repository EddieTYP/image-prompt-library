# Unreleased

## Local access protection

The app now checks the requested hostname before serving pages, images, or API responses. Localhost and literal IP addresses continue to work, including LAN access when enabled. If you use a custom hostname, add it to `IMAGE_PROMPT_LIBRARY_ALLOWED_HOSTS` before starting the server. See the [installation guide](../INSTALLATION.md).

## Public demo export

The demo exporter now rebuilds its data from the checked-in sample manifests and checksum-verified sample image packages. It no longer reads an existing Library, so private notes, prompts, or images added to sample cards cannot be included accidentally. The export command now requires both sample image packages; see [sample data instructions](../../sample-data/README.md#build-the-public-web-demo).

Your local Library and existing cards are unchanged. Exporting demo files does not publish them.
