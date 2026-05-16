from worlds.LauncherComponents import components, Component, Type as ComponentType
import logging
import Utils
from Utils import __version__ as __ap_version__
import sys
import platform
# We patch this because AP can't keep its hands to itself and has to start a thread to clean stuff up.
# We could monkey patch the hell out of it but since it's an inner function, I feel like the complexity
# of it is unreasonable compared to just reimplement a logger
# especially since it allows us to not have to cheat user_path

# Taken from https://github.com/ArchipelagoMW/Archipelago/blob/0.5.1.Hotfix1/Utils.py#L488
# and removed everythinhg that had to do with files, typing and cleanup
def patched_init_logging(
        name,
        loglevel = logging.INFO,
        write_mode = "w",
        log_format = "[%(name)s at %(asctime)s]: %(message)s",
        exception_logger = None,
        *args,
        **kwargs
):
    loglevel: int = Utils.loglevel_mapping.get(loglevel, loglevel)
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        handler.close()
    root_logger.setLevel(loglevel)

    class Filter(logging.Filter):
        def __init__(self, filter_name, condition) -> None:
            super().__init__(filter_name)
            self.condition = condition

        def filter(self, record: logging.LogRecord) -> bool:
            return self.condition(record)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.addFilter(Filter("NoFile", lambda record: not getattr(record, "NoStream", False)))
    root_logger.addHandler(stream_handler)

    # Relay unhandled exceptions to logger.
    if not getattr(sys.excepthook, "_wrapped", False):  # skip if already modified
        orig_hook = sys.excepthook

        def handle_exception(exc_type, exc_value, exc_traceback):
            if issubclass(exc_type, KeyboardInterrupt):
                sys.__excepthook__(exc_type, exc_value, exc_traceback)
                return
            logging.getLogger(exception_logger).exception("Uncaught exception",
                                                          exc_info=(exc_type, exc_value, exc_traceback))
            return orig_hook(exc_type, exc_value, exc_traceback)

        handle_exception._wrapped = True

        sys.excepthook = handle_exception

    logging.info(
        f"Archipelago ({__ap_version__}) logging initialized"
        f" on {platform.platform()}"
        f" running Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )


def launch_client(*args):
    from worlds.LauncherComponents import launch
    from .fuzz import launch as fuzz_launch
    
    import settings
    import yaml
    settings.no_gui = True
    settings.skip_autosave = True
    Utils.init_logging = patched_init_logging
    # See https://github.com/yaml/pyyaml/issues/103
    yaml.SafeDumper.ignore_aliases = lambda *args: True

    launch(fuzz_launch, name="Fuzzer", args=args)

components.append(Component("Fuzzer",None, func=launch_client, component_type=ComponentType.CLIENT))