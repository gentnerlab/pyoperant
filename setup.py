from distutils.core import setup, Extension
import os

# def read(fname):
#     return open(os.path.join(os.path.dirname(__file__), fname)).read()

comedi_poll = Extension('comedi_poll',
                    # include_dirs = ['/usr/local/include'],
                    libraries = ['comedi'],
                    # library_dirs = ['/usr/local/lib'],
                    sources = ['src/comedi_poll.c'])

setup(
    name = 'pyoperant',
    version = '0.1.2',
    author = 'Justin Kiggins',
    author_email = 'justin.kiggins@gmail.com',
    description = 'hardware interface and controls for operant conditioning',
    long_description = open('docs/README.rst', 'rt').read(),
    packages = ['pyoperant'],
    requires = ['pyephem','numpy'],
    scripts = [
        'scripts/behave',
        'scripts/pyoperantctl',
        'scripts/allsummary.py',
        ],
    license = "BSD",
    classifiers = [
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: GNU Affero General Public License v3",
        "Natural Language :: English",
        "Operating System :: Unix",
        "Programming Language :: Python :: 2.7",
        "Topic :: Scientific/Engineering",
        ],
#     ext_modules = [comedi_poll]
    )
