def classFactory(iface):
    from .olsztyn_geoportal import OlsztynGeoportal
    return OlsztynGeoportal(iface)