"This script should run from a msys shell, not from a Windows CMD shell."

# Requires tqdm, requests, and pytest:
#
# pip install tqdm
# pip install pytest
# pip install requests

import sys
import os
import re
import subprocess as sp
import logging

logger = logging.getLogger(__name__)

from tqdm import tqdm
import requests
import urllib 


codepath = r"C:\Code"
toolpath = r"C:\Tools"


def make_toolpath():
    if not os.path.exists(toolpath):
        logger.info("Creating %s directory...", toolpath)
        os.mkdir(toolpath)
    else:
        logger.info("Directory %s already exists.", toolpath)

def downloadhttp(url, destpath):
    response = requests.get(url, stream=True)
    length = int(response.headers.get('Content-Length', '0'))
    chunk_size = pow(2, 14)
    with tqdm(total=length) as tq:
        with open(destpath, "wb") as handle:
            for data in response.iter_content(chunk_size):
                tq.update(len(data))
                handle.write(data)

def downloadftp(url, destpath):
    urllib.urlretrieve(url, destpath)

def download(url, destpath):
    if url.startswith('ftp:'):
        downloadftp(url, destpath)
    else:
        downloadhttp(url, destpath)


def test_download(tmpdir):
    url = str("https://www.eol.ucar.edu/system/files/software/"
              "aeros/rhel-6/aeros-4928.rhel6_.tar.gz")
    url = str("http://www.eol.ucar.edu/system/files/images/book/"
              "Current%20and%20Upcoming%20Deployments/"
              "current_deployments_banner.png")
    download(url, os.path.join(str(tmpdir), "null"))


def mingwinpath(path):
    "Convert a Windows path to mingwin."
    path = re.sub(r"([A-Za-z]):\\", (lambda rx: "/"+rx.group(1).lower()+"/"),
                  path)
    path = re.sub(r"\\", "/", path)
    return path


class SubPatch(object):
    """
    A SubPatch designates a file in the source tree which must be patched
    using a regex substitution.
    """
    def __init__(self, sfile, subs):
        """
        Keep a list of (pattern, repl) tuples to be applied to
        sfile to patch it.
        """ 
        self.sfile = sfile
        self.subs = subs

    def editContent(self, content, settings=None):
        for sub in self.subs:
            pattern = sub[0]
            repl = sub[1]
            if settings:
                pattern = pattern % settings
                repl = repl % settings
            content = re.sub(pattern, repl, content,
                             count=0, flags=re.MULTILINE)
        return content

    def backupFile(self, efile):
        bak = efile+".orig"
        if not os.path.exists(bak):
            try:
                os.rename(efile, bak)
                logger.info("Backed up %s to %s" % (efile, bak))
            except OSError, e:
                logger.error("Cannot make backup file: %s" % str(e))
        else:
            logger.info("Backup already exists: %s" % (bak))

    def apply(self, pkg):
        efile = pkg.getSourcePath(self.sfile)
        logger.info("Fixing %s" % (efile))
        content = None
        with open(efile, "rb") as fd:
            content = fd.read()
        self.backupFile(efile)
        content = self.editContent(content, pkg.settings)
        with open(efile, "wb") as fd:
            fd.write(content)        


class Package(object):

    def __init__(self, name, url, pfile=None, srcdir=None):
        self.name = name
        self.url = url
        self.pfile = pfile
        self.srcdir = srcdir
        self.commands = None
        self.patches = []
        self.settings = {}
        if not self.pfile:
            self.pfile = self.fileFromURL(self.url)
        if not self.srcdir:
            self.srcdir = self.sourceDirFromPackageFile(self.pfile)
        self.setCommands("""
sh ./configure --prefix=/usr/local
make
make install
""")

    def update(self, variables):
        "Update the settings dictionary."
        self.settings.update(variables)

    def fileFromURL(self, url):
        return os.path.basename(url)

    def sourceDirFromPackageFile(self, pfile):
        return re.sub(r"(\.tar\.gz|\.7z|\.exe|\.zip|\.tar\.bz2)$", "", pfile)
    
    def getDownloadFile(self):
        "Derive a local path for the URL and download it if not found."
        filename = self.pfile
        downloads = r"%(USERPROFILE)s\Downloads" % os.environ
        logger.info("Download directory: %s", downloads)
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
            return ["tar", "--no-same-owner", "-xzf", mingwinpath(archive)]
        if archive.endswith(".7z"):
            return ["7z", "x", archive]
        if archive.endswith(".tar.bz2"):
            return ["tar", "--bzip2", "--no-same-owner",
                    "-xf", mingwinpath(archive)]
        return None

    def setCommands(self, text):
        if text is None:
            self.commands = []
        else:
            self.commands = text.strip().splitlines()
        return self

    def getCommands(self):
        return self.commands

    def runCommand(self, cmd, cwd):
        cstring = ""
        if cwd:
            cstring = "CMD=%s " % (cwd)
        if isinstance(cmd, str):
            cmd = cmd % self.settings
            cstring += cmd
        else:
            cmd = [c % self.settings for c in cmd]
            cstring += " ".join(cmd)
        logger.info(cstring)
        xp = sp.Popen(cmd, cwd=cwd)
        xp.wait()
        return xp

    def setPatches(self, patches):
        self.patches = patches
        return self
       
    def getSourcePath(self, sfile=None):
        path = os.path.join(codepath, self.srcdir)
        if sfile:
            path = os.path.join(path, sfile)
        return path

    def checkoutSubversion(self):
        "Use the URL as a subversion repo to checkout."
        srcdir = self.getSourcePath()
        if os.path.exists(srcdir):
            # For now, do not automatically update.
            logger.info("%s: checkout exists: %s" % (self.name, srcdir))
            return
        cmd = ['svn', 'co', self.url, self.srcdir]
        svn_ = self.runCommand(cmd, codepath)

    def unpack(self):
        if 'svn.' in self.url:
            self.checkoutSubversion()
            return
        archive = self.getDownloadFile()
        srcdir = self.getSourcePath()
        if os.path.exists(srcdir):
            logger.info("%s: %s already exists." % (self.name, srcdir))
        else:
            logger.info("%s: %s does not exist, extracting..." %
                        (self.name, srcdir))
            cmd = self.getUnpackCommand(archive)
            xp = self.runCommand(cmd, codepath)
            if xp.returncode == 2 and cmd[0] == "tar":
                logger.info("ignoring exit code 2 from tar")
            elif xp.returncode != 0:
                sys.exit(1)

    def applyPatches(self):
        for p in self.patches:
            p.apply(self)

    def build(self):
        self.unpack()
        self.applyPatches()
        srcdir = self.getSourcePath()
        if not os.path.exists("/usr/local"):
            os.mkdir("/usr/local")
        cmds = self.getCommands()
        for cmd in cmds:
            bp = self.runCommand(cmd, srcdir)
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
 --build-dir=boost-build --toolset=gcc --prefix=/usr/local --build-type=minimal
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

# the log4cpp configure check for pthreads fails with errors about redefining
# struct timespec, so circumvent that by defining _TIMESPEC_DEFINED.  Likewise
# code in log4cpp/include/log4cpp/config-MinGW32.h tries to define 
_log4cpp_112 = """
env CPPFLAGS="-D_TIMESPEC_DEFINED -DLOG4CPP_HAVE_INT64_T" sh ./configure --enable-static --disable-shared --prefix=/usr/local
make
make install
"""

_log4cpp = """
env CPPFLAGS="-D_TIMESPEC_DEFINED" sh ./configure --enable-static --disable-shared --prefix=/usr/local
make
make install
"""

_log4cpp_patches = [
    SubPatch("include/log4cpp/config-MinGW32.h",
             [(r"/?\*?(#define int64_t __int64)\*?/?", r"/*\1*/")]),
    ]


qwt = Package('qwt',
              'https://svn.code.sf.net/p/qwt/code/branches/qwt-6.0')
qwt.update({'QWTDIR':'C:/Tools/MinGW/msys/1.0/local/qwt',
            'QTDIR':'C:/Tools/Qt/4.6.2'})
qwt.setPatches([
    SubPatch("qwtconfig.pri",
             [(r"^(\s*)QWT_INSTALL_PREFIX(\s*)=.*$",
               r"\1QWT_INSTALL_PREFIX\2= %(QWTDIR)s"),
              (r"^\s*(QWT_CONFIG\s*\+= QwtDll)\s*$", r"# \1"),
              (r"^\s*(QWT_CONFIG\s*\+= QwtDesigner)\s*$", r"# \1"),
              (r"^\s*(QWT_CONFIG\s*\+= QwtExamples)\s*$", r"# \1")])
]).setCommands("""
mkdir -p %(QWTDIR)s/lib %(QWTDIR)s/lib %(QWTDIR)s/lib64
env QTDIR=%(QTDIR)s qmake -nocache -r QMAKE_MOC=%(QTDIR)s/bin/moc -spec win32-g++
make
make install
""")

log4cpp = Package("log4cpp",
                  "http://downloads.sourceforge.net/project/log4cpp/"
                  "log4cpp-1.1.x%20%28new%29/log4cpp-1.1/log4cpp-1.1.tar.gz?"
                  "r=https%3A%2F%2Fsourceforge.net%2Fprojects%2Flog4cpp"
                  "%2Ffiles%2Flog4cpp-1.1.x%2520%2528new%2529%2Flog4cpp-1.1%2F"
                  "&ts=1455745885&use_mirror=iweb",
                  "log4cpp-1.1.tar.gz",
                  srcdir="log4cpp")
log4cpp.setCommands(_log4cpp)
log4cpp.setPatches(_log4cpp_patches)

netcdf = Package("netcdf",
                 "ftp://ftp.unidata.ucar.edu/pub/netcdf/old/"
                 "netcdf-4.2.1.tar.gz")
netcdf.setCommands("""
sh ./configure --disable-netcdf-4 --disable-shared --prefix=/usr/local
make
make install
""")

netcdfcxx = Package("netcdf-cxx",
                    "ftp://ftp.unidata.ucar.edu/pub/netcdf/"
                    "netcdf-cxx-4.2.tar.gz")
netcdfcxx.setCommands("""
sh ./configure --disable-shared --prefix=/usr/local CPPFLAGS="-I /usr/local/include"
make
make install
""")

b2opts="""
threading=multi
toolset=gcc
variant=release
link=static
runtime-link=static
--prefix=C:/Tools/MinGW/msys/1.0/local
--layout=system
--build-type=minimal
--reconfigure
"""
b2opts=" ".join(b2opts.split())

pkglist = [
    Package("rapidee",
            "http://www.rapidee.com/download/RapidEE_setup.exe"),
    Package("qt",
            "https://download.qt.io/archive/qt/4.6/"
            "qt-win-opensource-4.6.2-mingw.exe"),
    # This is the latest Qt 4 available, but it requires MinGQ with
    # gcc 4.8.2, whereas the latest MinGW GCC tools package seems to be
    # gcc 4.8.1.
    Package("qt-4.8.6-gcc-4.8.2",
            "https://download.qt.io/archive/qt/4.6/"
            "qt-win-opensource-4.6.4-mingw.exe"),
    Package("qt-4.8.5",
            "https://download.qt.io/archive/qt/4.8/4.8.5/"
            "qt-win-opensource-4.8.5-mingw.exe"),
    Package("xerces-c", 
            "http://mirror.reverse.net/pub/apache//xerces/c/3/sources/"
            "xerces-c-3.1.2.tar.gz").setCommands(_xerces_cmds),
    log4cpp,
    Package("log4cpp-1.1.2rc1",
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
    Package("boost-1.42.0",
            "http://downloads.sourceforge.net/project/boost/boost/1.42.0/"
            "boost_1_42_0.7z?r=https%3A%2F%2Fsourceforge.net%2Fprojects%2F"
            "boost%2Ffiles%2Fboost%2F1.42.0%2F&ts=1455655701&use_mirror=iweb",
            "boost_1_42_0.7z").setCommands(" ".join(_bjam.strip().split())),
    Package("boost-1.60.0",
            "boost_1_60_0.tar.bz2",
            "boost_1_60_0.tar.bz2").setCommands("""
cmd /c "bootstrap.bat mingw"
b2 %s install
""" % (b2opts)),
    Package("sqlite",
            "http://www.sqlite.org/2016/sqlite-autoconf-3110000.tar.gz"),
    Package('proj.4',
            'http://download.osgeo.org/proj/proj-4.8.0.tar.gz'),
    Package('geos',
            "http://download.osgeo.org/geos/"
            "geos-3.5.0.tar.bz2").setCommands("""
env CPPFLAGS=-D__NO_INLINE__ sh ./configure --prefix=/usr/local
make
make install
"""),
    qwt,
    netcdf,
    netcdfcxx,
    Package('libecbufr',
            'http://svn.eol.ucar.edu/svn/eol/imports/libecbufr/trunk',
            srcdir='libecbufr').setCommands("""
env LDFLAGS="-lintl" sh ./configure --prefix=/usr/local
make install
""")
]

pkgmap = {pkg.name:pkg for pkg in pkglist}


aspen_packages = ['sqlite', 'proj.4', 'geos', 'netcdf', 'netcdfcxx']
# ['iconv', 'freexl', 'spatialite', 'libecbufr', 'kermit']

# ASPEN build notes:
#
# git clone git@github:/ncareol/aspen.git
# cd aspen/Aspen
# git submodule update --init
# cp config_windows.py config.py
# /c/python2.7/Scripts/scons.py


def build_xercesc():
    pkg = pkgmap["xerces-c"]
    pkg.unpack()
    pkg.build()


# Useful reference for attempting unattended installs of some of these packages:
# http://unattended.sourceforge.net/installers.php


def main():
    logging.basicConfig(level=logging.DEBUG)
    make_toolpath()
    for pname in sys.argv[1:]:
        pkg = pkgmap.get(pname)
        if not pkg:
            logger.error("No such package: %s" % (pname))
        else:
            logger.info("Building package: %s" % (pname))
            pkg.build()

if __name__ == "__main__":
    main()


def test_sourcedir():
    pkg = Package("boost", "url", "boost_1_42_0.7z")
    assert(pkg.sourceDirFromPackageFile(pkg.pfile) == "boost_1_42_0")
    

def test_mingwinpath():
    assert(mingwinpath(codepath) == "/c/Code")
    assert(mingwinpath(r"D:\DATA") == "/d/DATA")
    assert(mingwinpath(r"d:\DATA") == "/d/DATA")
    assert(mingwinpath(r"Users\granger") == "Users/granger")

_header = """
/* define if the compiler has int64_t */
#ifndef LOG4CPP_HAVE_INT64_T
#define LOG4CPP_HAVE_INT64_T
#define int64_t __int64

/* define if the compiler has in_addr_t */
#ifndef LOG4CPP_HAVE_IN_ADDR_T
#define LOG4CPP_HAVE_IN_ADDR_T
"""
_fixed_header = """
/* define if the compiler has int64_t */
#ifndef LOG4CPP_HAVE_INT64_T
#define LOG4CPP_HAVE_INT64_T
/*#define int64_t __int64*/

/* define if the compiler has in_addr_t */
#ifndef LOG4CPP_HAVE_IN_ADDR_T
#define LOG4CPP_HAVE_IN_ADDR_T
"""

def test_fix_header():
    patch = _log4cpp_patches[0]
    content = patch.editContent(_header)
    assert(content == _fixed_header)
    content = patch.editContent(content)
    assert(content == _fixed_header)


_qwt_pri = """
QWT_INSTALL_PREFIX = $$[QT_INSTALL_PREFIX]

unix {
    QWT_INSTALL_PREFIX    = /usr/local/qwt-$$QWT_VERSION-svn
}

win32 {
    QWT_INSTALL_PREFIX    = C:/Qwt-$$QWT_VERSION-svn
}
"""

_qwt_pri_fixed = """
QWT_INSTALL_PREFIX = C:/Tools/MinGW/msys/1.0/local/qwt

unix {
    QWT_INSTALL_PREFIX    = C:/Tools/MinGW/msys/1.0/local/qwt
}

win32 {
    QWT_INSTALL_PREFIX    = C:/Tools/MinGW/msys/1.0/local/qwt
}
"""

def test_qwt_pri():
    patch = qwt.patches[0]
    assert(qwt.settings['QWTDIR'] == 'C:/Tools/MinGW/msys/1.0/local/qwt')
    content = patch.editContent(_qwt_pri, qwt.settings)
    assert(content == _qwt_pri_fixed)
    content = patch.editContent(content, qwt.settings)
    assert(content == _qwt_pri_fixed)

