from ipywidgets.widgets import *
from traitlets import Unicode, List, Bool

from qcodes.widgets import display_auto


display_auto('widgets/toc_widget/main.css')
display_auto('widgets/toc_widget/toc_widget.js')


class TOCWidget(DOMWidget):
    _view_name = Unicode('TOCView').tag(sync=True)
    _view_module = Unicode('toc').tag(sync=True)
    _view_module_version = Unicode('0.1.0').tag(sync=True)
    _widget_name = Unicode('none').tag(sync=True)