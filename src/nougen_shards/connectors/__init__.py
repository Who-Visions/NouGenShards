"""Universal Database Connector Fabric."""


def query_external_dbs(*args, **kwargs):
    from .sql import query_external_dbs as _query_external_dbs
    return _query_external_dbs(*args, **kwargs)


__all__ = ["query_external_dbs"]
