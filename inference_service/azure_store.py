"""Azure-Zugriff über die verwaltete Identität des späteren Containers."""

from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
from azure.cosmos.exceptions import CosmosResourceNotFoundError


class BlobStore:
    def __init__(self, service):
        self.service = service

    def put_once(self, container, name, data):
        try:
            self.service.get_blob_client(container, name).upload_blob(data, overwrite=False)
            return True
        except ResourceExistsError:
            return False

    def read(self, container, name):
        return self.service.get_blob_client(container, name).download_blob().readall()

    def list_chunks(self, prefix):
        return [b.name for b in self.service.get_container_client("temporaer").list_blobs(name_starts_with=prefix)]

    def cleanup(self, prefix):
        for name in self.list_chunks(prefix):
            try:
                self.service.get_blob_client("temporaer", name).delete_blob()
            except ResourceNotFoundError:
                pass  # Bereits entfernt, beispielsweise bei erneuter Zustellung.


class CosmosResults:
    def __init__(self, container):
        self.container = container

    def get(self, device, measurement):
        try:
            return self.container.read_item(item=measurement, partition_key=device)
        except CosmosResourceNotFoundError:
            return None

    def save(self, document):
        # Messungs-ID und Geräte-ID ergeben einen stabilen Schlüssel.
        # Wiederholungen erzeugen damit kein zweites Ergebnisdokument.
        self.container.upsert_item(document)
