import os
import hashlib
import re

ROOT_PATH = './media/tmp/'


def random(n: int = 8):
    return hashlib.sha1(os.urandom(n)).hexdigest()


class TempFile:
    def __init__(self, fn = None):
        fn, ext = os.path.splitext(fn)
        fn = os.path.basename(fn)
        

        pref = (fn + "_") if fn is not None else ""
        self.fn = pref + random()
        while os.path.exists(self.path()):
            self.fn = pref + random()

        self.fn += ext

    def __enter__(self, *args):
        p = self.path()
        os.makedirs(ROOT_PATH, exist_ok=True)
        if not os.path.exists(p):
            f = open(p, "w+")
            f.close()

        return p

    def __exit__(self, *args):
        if os.path.exists(self.path()):
            os.remove(self.path())

    def path(self):
        return ROOT_PATH + self.fn


if __name__ == "__main__":
    with TempFile("test.png.gif.gamer") as fn:
        print("File created.")
        print(fn)
    print("File deleted.")