import shutil

import qmtlink


def main() -> None:
    assert qmtlink.__version__
    assert shutil.which("qmt") is not None
    assert shutil.which("qmtlink") is not None


if __name__ == "__main__":
    main()
