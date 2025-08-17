def classFactory(iface):
    from .digipin_encoder import DIGIPIN_ENCODER
    return DIGIPIN_ENCODER(iface)