from setuptools import find_packages, setup, Extension
#from distutils.core import setup, Extension
import socket

hnm = socket.gethostname()

# def read(fname):
#     return open(os.path.join(os.path.dirname(__file__), fname)).read()

if 'zog' in hnm:
    comedi_poll = Extension('comedi_poll',
                    include_dirs = ['/usr/local/include'],
                    libraries = ['comedi'],
                    library_dirs = ['/usr/local/lib'],
                    sources = ['src/comedi_poll.c'])

setup(
    name = 'pyoperant',
    packages=find_packages(),
    version = '0.2.0',
    author = 'Justin Kiggins',
    author_email = 'justin.kiggins@gmail.com',
    description = 'hardware interface and controls for operant conditioning',
    long_description = open('docs/README.rst', 'rt').read(),
    requires = ['pyephem','numpy'],
    scripts = [
        'scripts/behave',
        ],
    license = "BSD",
    classifiers = [
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: GNU Affero General Public License v3",
        "Natural Language :: English",
        "Operating System :: Unix",
        "Programming Language :: Python :: 3.6",
        "Topic :: Scientific/Engineering",
        ],
#     ext_modules = [comedi_poll]
    )
