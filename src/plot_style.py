"""
Academic Paper Plot Style Configuration
========================================
Unified plot style: white background, no grid, bold axis labels.

Usage:
    import plot_style
"""

import matplotlib.pyplot as plt

ACADEMIC_STYLE = {
    # Font
    'font.family': 'sans-serif',
    'font.sans-serif': ['Arial', 'DejaVu Sans'],
    'font.size': 12,

    # Axes
    'axes.linewidth': 1.2,
    'axes.labelsize': 16,
    'axes.labelweight': 'bold',
    'axes.titlesize': 13,
    'axes.titleweight': 'bold',
    'axes.facecolor': 'white',
    'axes.grid': False,

    # Ticks
    'xtick.labelsize': 12,
    'ytick.labelsize': 12,
    'xtick.major.width': 1.0,
    'ytick.major.width': 1.0,
    'xtick.major.size': 5,
    'ytick.major.size': 5,
    'xtick.minor.size': 3,
    'ytick.minor.size': 3,
    'xtick.direction': 'in',
    'ytick.direction': 'in',
    'xtick.top': False,
    'ytick.right': False,

    # Legend
    'legend.frameon': False,
    'legend.fontsize': 11,

    # Figure
    'figure.facecolor': 'white',
    'savefig.facecolor': 'white',
    'savefig.dpi': 300,
    'savefig.bbox': 'tight',

    # Lines
    'lines.linewidth': 1.5,
}


def apply_academic_style():
    """Apply academic paper plot style to global matplotlib rcParams."""
    plt.rcParams.update(ACADEMIC_STYLE)


def add_subplot_label(ax, label, x=-0.12, y=1.05, fontsize=16):
    """
    Add a bold subplot label (e.g. (a), (b), (c)) to an axes.
    """
    ax.text(x, y, label, transform=ax.transAxes, fontsize=fontsize,
            fontweight='bold', verticalalignment='bottom')


# Apply on import
apply_academic_style()
