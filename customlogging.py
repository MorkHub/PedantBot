import logging
from pedant_config import CONF,MESG
import sys
import os
try:
    """

    basic logging setup:
        INFO
        DEBUG
        WARNING
        ERROR

    """

    logging.basicConfig(format=CONF.get('log_format','[%(asctime)s] [%(levelname)s] %(message)s'), stream=sys.stdout, level=logging.INFO)
    logger = logging.getLogger('discord')
    logger.setLevel(logging.INFO)

    log_handler = logging.handlers.RotatingFileHandler(CONF.get('dir_pref','/home/shwam3/')+CONF.get('logfile','{}.log'.format(__file__)), 'a', backupCount=5, delay=True)
    log_handler.setLevel(logging.DEBUG)

    err_log_handler = logging.StreamHandler(stream=sys.stderr)
    err_log_handler.setLevel(logging.WARNING)

    formatter = logging.Formatter(CONF.get('log_format','[%(asctime)s] [%(levelname)s] %(message)s'))
    log_handler.setFormatter(formatter)
    err_log_handler.setFormatter(formatter)

    if os.path.isfile(CONF.get('dir_pref','/home/shwam3/')+CONF.get('logfile','{}.log'.format(__file__))):
        log_handler.doRollover()

    logger.addHandler(log_handler)
    logger.addHandler(err_log_handler)

    """

    logging for unauthorised sudo commands

    """

    permlog = logging.getLogger('sudo')
    permlog.setLevel(logging.WARNING)
    permlog_handler = logging.handlers.RotatingFileHandler('sudo.log','a',backupCount=0,delay=True)
    permlog_formatter = logging.Formatter('[%(asctime)s] %(message)s')
    permlog_handler.setFormatter(permlog_formatter)
    permlog.addHandler(permlog_handler)

    """

    logging for pedant-audit logs

    """

    auditlog = logging.getLogger('audit-log')
    auditlog.setLevel(logging.WARNING)
    auditlog_handler = logging.handlers.RotatingFileHandler('audit.log','a',backupCount=0,delay=True)
    auditlog_formatter = logging.Formatter('[%(asctime)s] %(message)s')
    auditlog_handler.setFormatter(auditlog_formatter)
    auditlog.addHandler(auditlog_handler)

except Exception as e:
    print(e)

