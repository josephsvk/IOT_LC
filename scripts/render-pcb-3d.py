#!/usr/bin/env python3
"""Render clean top/bottom PCB views without non-physical drawing layers."""
from pathlib import Path
import argparse
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
BOARD = ROOT / 'IOT_LC.kicad_pcb'
PROJECT = ROOT / 'IOT_LC.kicad_pro'
OUTPUT = ROOT / 'docs/images'
KEEP_LAYERS = {'F.Cu', 'B.Cu', 'F.Mask', 'B.Mask', 'F.SilkS', 'B.SilkS', 'Edge.Cuts'}
DRAWINGS = {
    'gr_line', 'gr_arc', 'gr_rect', 'gr_circle', 'gr_poly', 'gr_curve',
    'gr_text', 'gr_text_box', 'dimension', 'target', 'image',
    'fp_line', 'fp_arc', 'fp_rect', 'fp_circle', 'fp_poly', 'fp_curve',
    'fp_text', 'fp_text_box', 'property',
}


def expr_end(source, start):
    depth = 0
    quoted = False
    escaped = False
    for i in range(start, len(source)):
        char = source[i]
        if quoted:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
            if depth == 0:
                return i + 1
    raise ValueError('Unbalanced KiCad board expression')


def atom_end(source, start):
    if source[start] == '"':
        escaped = False
        for i in range(start + 1, len(source)):
            if escaped:
                escaped = False
            elif source[i] == '\\':
                escaped = True
            elif source[i] == '"':
                return i + 1
        raise ValueError('Unterminated quoted atom')
    i = start
    while i < len(source) and not source[i].isspace() and source[i] not in '()':
        i += 1
    return i


def children(source, start, end):
    """Yield direct child expressions in a parent expression."""
    i = start + 1
    while i < end - 1 and source[i].isspace():
        i += 1
    head_end = atom_end(source, i)
    i = head_end
    while i < end - 1:
        while i < end - 1 and source[i].isspace():
            i += 1
        if i >= end - 1:
            break
        if source[i] == ';':
            newline = source.find('\n', i, end)
            i = end - 1 if newline < 0 else newline + 1
        elif source[i] == '(':
            child_end = expr_end(source, i)
            yield i, child_end
            i = child_end
        else:
            i = atom_end(source, i)


def head(source, start):
    i = start + 1
    while source[i].isspace():
        i += 1
    end = atom_end(source, i)
    return source[i:end]


def layer(source, start, end):
    for child_start, child_end in children(source, start, end):
        if head(source, child_start) == 'layer':
            match = re.match(r'\(\s*layer\s+"([^"]+)"', source[child_start:child_end])
            return match.group(1) if match else None
    return None


def clean_board(source, exclude_dnp=False):
    root_end = expr_end(source, source.index('('))
    removals = []
    for start, end in children(source, source.index('('), root_end):
        item_head = head(source, start)
        if item_head == 'footprint':
            footprint_children = list(children(source, start, end))
            is_dnp = any(
                head(source, child_start) == 'attr'
                and re.search(r'\bdnp\b', source[child_start:child_end])
                for child_start, child_end in footprint_children
            )
            # `pcb render` has no --no-dnp option; emulate it on this disposable copy.
            if exclude_dnp and is_dnp:
                removals.append((start, end))
                continue
            for nested_start, nested_end in footprint_children:
                nested_head = head(source, nested_start)
                if nested_head in DRAWINGS and layer(source, nested_start, nested_end) not in KEEP_LAYERS:
                    removals.append((nested_start, nested_end))
        elif item_head in DRAWINGS and layer(source, start, end) not in KEEP_LAYERS:
            removals.append((start, end))
    for start, end in sorted(removals, reverse=True):
        source = source[:start] + source[end:]
    return source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--no-dnp', action='store_true',
                        help='exclude DNP footprints from the render')
    args = parser.parse_args()
    if not BOARD.is_file() or not PROJECT.is_file():
        raise FileNotFoundError('Expected IOT_LC.kicad_pcb and IOT_LC.kicad_pro')
    OUTPUT.mkdir(parents=True, exist_ok=True)
    temporary_root = Path(tempfile.mkdtemp(prefix='.iot-lc-render-', dir=ROOT))
    try:
        temporary_board = temporary_root / 'IOT_LC_render.kicad_pcb'
        temporary_project = temporary_root / 'IOT_LC_render.kicad_pro'
        temporary_board.write_text(
            clean_board(BOARD.read_text(encoding='utf-8'), exclude_dnp=args.no_dnp),
            encoding='utf-8',
        )
        project_text = PROJECT.read_text(encoding='utf-8')
        project_text = project_text.replace('"filename": "IOT_LC.kicad_pro"',
                                            '"filename": "IOT_LC_render.kicad_pro"')
        temporary_project.write_text(project_text, encoding='utf-8')
        for side, silk in (('top', 'F.SilkS'), ('bottom', 'B.SilkS')):
            target = OUTPUT / f'pcb-3d-{side}.png'
            dnp_status = 'excluded' if args.no_dnp else 'included'
            print(f'Rendering {side} view (including {silk}; DNP footprints {dnp_status})', flush=True)
            subprocess.run([
                'kicad-cli', 'pcb', 'render', '--output', str(target),
                '--width', '2200', '--height', '1500', '--side', side,
                '--background', 'opaque', '--quality', 'high',
                '--preset', 'follow_pcb_editor', '--use-board-stackup-colors', '--floor',
                str(temporary_board),
            ], check=True)
        print('Generating project-root SMD outputs', flush=True)
        result = subprocess.run([
            sys.executable,
            str(ROOT / 'scripts' / 'generate-smd-outputs.py'),
        ], check=False)
        if result.returncode:
            # Stale production BOM/position inputs should not prevent the
            # documentation render and Git backup from completing. The SMD
            # generator reports the specific issue; its previous outputs are
            # left untouched.
            print('SMD output generation failed; keeping existing SMD files and continuing documentation export.', flush=True)
    finally:
        shutil.rmtree(temporary_root, ignore_errors=True)


if __name__ == '__main__':
    main()
