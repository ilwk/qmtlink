import shutil
from importlib.util import find_spec

import qmtlink


def main() -> None:
    assert qmtlink.__version__
    assert shutil.which("qmtlink") is not None
    assert find_spec("qmtlink.client") is None
    assert find_spec("qmtlink.cli") is None
    assert find_spec("fastapi") is not None
    assert find_spec("uvicorn") is not None


if __name__ == "__main__":
    main()
