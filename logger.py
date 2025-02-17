import logging
from colorlog import ColoredFormatter

def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    if not logger.handlers:
        # Console handler with color
        handler = logging.StreamHandler()
        handler.setLevel(logging.DEBUG)

        # Assign colors to log levels, including our custom level
        formatter = ColoredFormatter(
            "%(log_color)s%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            log_colors={
                'DEBUG': 'green',
                'INFO': 'blue',
                'WARNING': 'light_red',
                'ERROR': 'red',
                'CRITICAL': 'bold_red',
            }
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger
