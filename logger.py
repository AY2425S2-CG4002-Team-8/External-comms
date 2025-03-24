import logging
from colorlog import ColoredFormatter

# Define custom log levels
AI_P1_LEVEL = 25  # Between WARNING (30) and INFO (20)
AI_P2_LEVEL = 26  # Slightly higher than AI_P1

logging.addLevelName(AI_P1_LEVEL, "AI_P1")
logging.addLevelName(AI_P2_LEVEL, "AI_P2")

def ai_p1(self, message, *args, **kwargs):
    if self.isEnabledFor(AI_P1_LEVEL):
        self._log(AI_P1_LEVEL, message, args, **kwargs)

def ai_p2(self, message, *args, **kwargs):
    if self.isEnabledFor(AI_P2_LEVEL):
        self._log(AI_P2_LEVEL, message, args, **kwargs)

logging.Logger.ai_p1 = ai_p1
logging.Logger.ai_p2 = ai_p2


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
                'CRITICAL': 'white',
                'AI_P1': 'cyan',
                'AI_P2': 'magenta',
            }
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger
