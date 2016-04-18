# Qcodes

Qcodes is a Python-based data acquisition framework developed by the Copenhagen / Delft / Sydney / Microsoft quantum computing consortium. While it has been developed to serve the needs of nanoelectronic device experiments, it is not inherently limited to such experiments, and can be used anywhere a system with many degrees of freedom is controllable by computer.

Qcodes has taken inspiration from many similar frameworks that have come before it, including:
- [QTLab](https://github.com/heeres/qtlab)
- [Special Measure](https://github.com/yacobylab/special-measure)
- "Alex Igor Procedures" see [thesis](http://qdev.nbi.ku.dk/student_theses/pdf_files/A_Johnson_thesis.pdf) appendix D and [successors](http://www.igorexchange.com/project/Expt_Procedures)
- and countless smaller components created by students and postdocs throughout the quantum computing community

Qcodes is compatible with Python 3.3+. It is primarily intended for use from Jupyter notebooks, but can be used from traditional terminal-based shells and in stand-alone scripts as well.

## Installation

We recommend [Anaconda](https://www.continuum.io/downloads) as an easy way to get most of the dependencies out-of-the-box.

As the project is still private, install it directly from this repository:

- Install git: the [command-line toolset](https://git-scm.com/) is the most powerful but the [desktop GUI from github](https://desktop.github.com/) is also quite good

- Clone this repository somewhere on your hard drive. If you're using command line git, open a terminal window in the directory where you'd like to put qcodes and type:
```
git clone https://github.com/qdev-dk/Qcodes.git
```

- Register it with Python, and install dependencies if any are missing: run this from the root directory of the repository you just cloned:
```
python setup.py develop
```

Now Qcodes should be available to import into all Python sessions you run. To test, run `python` from some other directory (not where you just ran `setup.py`) and type `import qcodes`. If it works without an error you're ready to go.

### Plotting Requirements

Because these can sometimes be tricky to install (and not everyone will want all of them), the plotting packages are not set as required dependencies, so setup.py will not automatically install them. You can install them with `pip`:

- For `qcodes.MatPlot`: matplotlib version 1.5 or higher
- For `qcodes.QtPlot`: pyqtgraph version 0.9.10 or higher

### Updating Qcodes

If you registered Qcodes with Python via `setup.py develop`, all you need to do to get the latest code is open a terminal window pointing to anywhere inside the repository and run `git pull`

## Usage

See the [docs](docs) directory, particularly the notebooks in [docs/examples](docs/examples)

Until we have this prepared as an installable package, you need to make sure Python can find qcodes by adding the repository root directory to `sys.path`:
```
import sys
qcpath = 'your/Qcodes/repository/path'
if qcpath not in sys.path:
    sys.path.append(qcpath)
```

## Contributing

See [Contributing](CONTRIBUTING.md) for information about bug/issue reports, contributing code, style, and testing

See the [Roadmap](ROADMAP.md) an overview of where the project intends to go.

## License

Qcodes is currently a private development of Microsoft's Station Q collaboration, and IS NOT licensed for distribution outside the collaboration. We intend to release it as open source software once it is robust and reasonably stable, under the MIT license or similar. See [License](LICENSE.txt)