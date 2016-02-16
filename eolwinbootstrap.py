"This script must run from a msys shell, not from a Windows CMD shell."

import sys
import os
import re
import subprocess as sp
import logging

logger = logging.getLogger(__name__)

from tqdm import tqdm
import requests


codepath = r"C:\Code"
toolpath = r"C:\Tools"
downloads = r"%(USERPROFILE)s\Downloads" % os.environ

logger.info("Download directory: %s", downloads)


def make_toolpath():
    if not os.path.exists(toolpath):
        logger.info("Creating %s directory...", toolpath)
        os.mkdir(toolpath)
    else:
        logger.info("Directory %s already exists.", toolpath)

def download(url, destpath):
    response = requests.get(url, stream=True)
    with open(destpath, "wb") as handle:
        for data in tqdm(response.iter_content()):
            handle.write(data)

def mingwinpath(path):
    "Convert a Windows path to mingwin."
    path = re.sub(r"([ABCDEF]):\\", (lambda rx: "/"+rx.group(1).lower()+"/"),
                  path)
    path = re.sub(r"\\", "/", path)
    return path


class Package(object):

    def __init__(self, name, url, pfile=None, srcdir=None):
        self.name = name
        self.url = url
        self.pfile = pfile
        self.srcdir = srcdir
        if not self.pfile:
            self.pfile = self.fileFromURL(self.url)
        if not self.srcdir:
            self.srcdir = self.sourceDirFromPackageFile(self.pfile)

    def fileFromURL(self, url):
        return os.path.basename(url)

    def sourceDirFromPackageFile(self, pfile):
        return re.sub(r"(\.tar\.gz|\.7z|\.exe|\.zip|\.bz2)$", "", pfile)
    
    def getDownloadFile(self):
        "Derive a local path for the URL and download it if not found."
        filename = self.pfile
        destpath = os.path.join(downloads, filename)
        return self.findOrDownload(self.url, destpath)

    def findOrDownload(self, url, destpath):
        "If destpath does not exist, download it from the URL."
        if not os.path.exists(destpath):
            logger.debug("Download destination not found: %s", destpath)
            download(url, destpath)
        else:
            logger.info("Download already exists: %s", destpath)
        return destpath

    def getUnpackCommand(self, archive):
        if archive.endswith(".tar.gz"):
            return ["tar", "xzf", mingwinpath(archive)]
        if archive.endswith(".7z"):
            return ["7z", "x", archive]
        return None

    def setCommands(self, text):
        self.commands = text.strip().splitlines()
        return self

    def getCommands(self):
        return self.commands

    def getSourcePath(self):
        return os.path.join(codepath, self.srcdir)

    def unpack(self):
        archive = self.getDownloadFile()
        srcdir = self.getSourcePath()
        if os.path.exists(srcdir):
            logger.info("%s: %s already exists." % (self.name, srcdir))
        else:
            logger.info("%s: %s does not exist, extracting..." %
                        (self.name, srcdir))
            cmd = self.getUnpackCommand(archive)
            logger.info(" ".join(cmd))
            xp = sp.Popen(cmd, cwd=codepath)
            xp.wait()
            if xp.returncode != 0:
                sys.exit(1)

    def build(self):
        self.unpack()
        srcdir = self.getSourcePath()
        if not os.path.exists("/usr/local"):
            os.mkdir("/usr/local")
        cmds = self.getCommands()
        for cmd in cmds:
            logger.info("CWD=" + srcdir + " " + cmd)
            bp = sp.Popen(cmd, cwd=srcdir)
            bp.wait()
            if bp.returncode != 0:
                sys.exit(1)

# log4cpp: I considered cloning the codegit code from sourforge, but then
# we do not get the generated configure script, and I would rather not have
# to install the auto tools on msys also.  So stick with the package
# download.

# The xerces configure script must be run explicitly with the msys sh.
_xerces_cmds = """
sh ./configure --enable-static --disable-shared --prefix=/usr/local
make libxerces_c_la_LDFLAGS="-release 3.1 -no-undefined"
make install
"""

_bjam = """
bjam
 --build-dir=boost-build --toolset=gcc --prefix=/usr/local --build-type=minimal \
 --with-date_time
 --with-test
 --with-serialization
 --with-program_options
 --with-regex
 --with-filesystem
 --with-system
 link=static
 install
"""

_log4cpp = """
sh ./configure --enable-static --disable-shared --prefix=/usr/local
make
make install
"""

pkglist = [
    Package("rapidee",
            "http://www.rapidee.com/download/RapidEE_setup.exe"),
    Package("qt",
            "https://download.qt.io/archive/qt/4.6/"
            "qt-win-opensource-4.6.2-mingw.exe"),
    Package("xerces-c", 
            "http://mirror.reverse.net/pub/apache//xerces/c/3/sources/"
            "xerces-c-3.1.2.tar.gz").setCommands(_xerces_cmds),
    Package("log4cpp",
            "http://downloads.sourceforge.net/project/log4cpp/log4cpp-1.1.x"
            "%20%28new%29/log4cpp-1.1/log4cpp-1.1.2rc1.tar.gz?r="
            "https%3A%2F%2Fsourceforge.net%2Fprojects%2Flog4cpp%2Ffiles%2F&ts="
            "1455654669&use_mirror=iweb",
            "log4cpp-1.1.2rc1.tar.gz",
            srcdir="log4cpp").setCommands(_log4cpp),
    Package("7zip",
            "http://www.7-zip.org/a/7z1514.exe"),
    Package("git",
            "https://github.com/git-for-windows/git/releases/download/"
            "v2.7.1.windows.1/Git-2.7.1-32-bit.exe"),
    Package("boost",
            "http://downloads.sourceforge.net/project/boost/boost/1.42.0/"
            "boost_1_42_0.7z?r=https%3A%2F%2Fsourceforge.net%2Fprojects%2F"
            "boost%2Ffiles%2Fboost%2F1.42.0%2F&ts=1455655701&use_mirror=iweb",
            "boost_1_42_0.7z").setCommands(" ".join(_bjam.strip().split()))
]

pkgmap = { pkg.name:pkg for pkg in pkglist }


def build_xercesc():
    pkg = pkgmap["xerces-c"]
    pkg.unpack()
    pkg.build()


# Useful reference for attempting unattended installs of some of these packages:
# http://unattended.sourceforge.net/installers.php


boostpath = os.path.join(codepath, "boost_1_42_0")

def build_boost():
    os.chdir(boostpath)
    os.execvp("bjam", bjam.strip().split())
    

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    make_toolpath()
    pkg = None
    if len(sys.argv) > 1:
        pname = sys.argv[1]
        pkg = pkgmap.get(pname)
        if not pkg:
            print("No such package: %s" % (pname))
    if pkg:
        pkg.build()



def test_sourcedir():
    pkg = Package("boost", "url", "boost_1_42_0.7z")
    assert(pkg.sourceDirFromPackageFile(pkg.pfile) == "boost_1_42_0")
    

def test_mingwinpath():
    assert(mingwinpath(codepath) == "/c/Code")
    assert(mingwinpath(r"D:\DATA") == "/d/DATA")
    assert(mingwinpath(r"Users\granger") == "Users/granger")

