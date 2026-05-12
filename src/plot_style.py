"""
Academic Paper Plot Style Configuration
========================================
Unified plot style for the entire project:
white background, no grid, bold axis labels, bold subplot labels.

Usage:
    Add at the top of any file that produces plots:
        import plot_style

    The style is applied automatically on import.
"""

import matplotlib.pyplot as plt

# Academic paper style parameters
ACADEMIC_STYLE = {
    # Font settings
    'font.family': 'sans-serif',
    'font.sans-serif': ['Arial', 'DejaVu Sans'],
    'font.size': 12,

    # Axes
    'axes.linewidth': 1.2,
    'axes.labelsize': 14,
    'axes.labelweight': 'bold',
    'axes.titlesize': 13,
    'axes.titleweight': 'bold',
    'axes.facecolor': 'white',
    'axes.grid': False,

    # Tick marks
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
    'xtick.top': True,
    'ytick.right': True,

    # Legend
    'legend.frameon': False,
    'legend.fontsize': 11,

    # Figure background
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

    Parameters:
        ax: matplotlib Axes object
        label: label text, e.g. '(a)'
        x, y: position in axes coordinates
        fontsize: font size (default 16 for clear visibility)
    """
    ax.text(x, y, label, transform=ax.transAxes, fontsize=fontsize,
            fontweight='bold', verticalalignment='bottom')


# Apply academic style on import
apply_academic_style()
