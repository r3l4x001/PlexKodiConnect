# -*- coding: utf-8 -*-
###############################################################################
import logging
import xbmc
###############################################################################
LEVELS = {
    logging.ERROR: xbmc.LOGERROR,
    logging.WARNING: xbmc.LOGWARNING,
    logging.INFO: xbmc.LOGNOTICE,
    logging.DEBUG: xbmc.LOGDEBUG
}
###############################################################################


def try_encode(uniString, encoding='utf-8'):
    """
    Will try to encode uniString (in unicode) to encoding. This possibly
    fails with e.g. Android TV's Python, which does not accept arguments for
    string.encode()
    """
    if isinstance(uniString, str):
        # already encoded
        return uniString
    try:
        uniString = uniString.encode(encoding, "ignore")
    except TypeError:
        uniString = uniString.encode()
    return uniString


def config():
    logger = logging.getLogger('PLEX')
    logger.addHandler(LogHandler())
    logger.setLevel(logging.DEBUG)


class LogHandler(logging.StreamHandler):
    def __init__(self):
        logging.StreamHandler.__init__(self)
        self.setFormatter(logging.Formatter(fmt="%(name)s: %(message)s"))

    def emit(self, record):
        try:
            xbmc.log(self.format(record), level=LEVELS[record.levelno])
        except UnicodeEncodeError:
            xbmc.log(try_encode(self.format(record)),
                     level=LEVELS[record.levelno])
