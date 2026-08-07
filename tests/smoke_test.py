import shutil
from importlib.util import find_spec

import qmtlink


def main() -> None:
    assert qmtlink.__version__
    assert shutil.which("qmt") is not None
    assert shutil.which("qmtlink") is not None
    assert find_spec("fastapi") is None
    assert find_spec("uvicorn") is None
    assert find_spec("xtquant") is None


if __name__ == "__main__":
    main()
