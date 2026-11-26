# DAT Texture Wizard (DTW)

## About this Linux port

Hey! This project aims to let DAT Texture Wizard run natively on Linux, without
having to use Bottles or Wine. AI tools were used to assist with translating
and adapting parts of the original Windows version and with the compatibility
work needed to make this native Linux version possible.

Head to the downloads page **[Here](https://github.com/ttmporting/DAT-Texture-Wizard/releases)**
to download the AppImage.

This is a beta of the Linux GUI port, not a claim that every feature of the
original Windows application has been ported. Review the
[Linux GUI guide](https://github.com/ttmporting/DAT-Texture-Wizard/blob/linux-port/README.GUI.LINUX.md)
for supported workflows, limitations, and launch instructions. Always keep
backups and save rebuilt disc images to a new file.

---

This program allows for disc (ISO/GCM) management of GameCube games, as well as texture exporting and importing, particularly for Super Smash Bros. Melee and 20XX HP. The internal file structure of HAL DAT files (such as stage/menu/character files) can also be deeply analyzed and edited.

Disc management features include adding/replacing/deleting files and/or folders (including replacing files that are larger than the original), building a disc from root files, editing the game names (short/long titles, descriptions, etc.), replacing the disc banner, and more.

You can find the official thread here: [DAT Texture Wizard on SmashBoards.com](https://smashboards.com/threads/dat-texture-wizard-current-version-6-1.373777/)

The structure of this program's code is largely a functional style (i.e. built mostly using just strait functions). Certainly some parts would be better suited as objects, with classes and their own personal methods. And I know there are some things that could be done more efficiently. A strong factor that led to some matters such as these is the fact that this is a really old project, built when I was first learning Python. :P But going forward I'll be occasionally refactoring parts of this program, and rewriting key components of it as I incorporate them into future projects. Let me know if there's anything you'd like to see broken out into a separate project, like HSD DAT file/structure objects, the texture codec, etc.

## Get the app

- **AppImage:** Download the latest Linux AppImage from the
  [GitHub Releases page](https://github.com/ttmporting/DAT-Texture-Wizard/releases).
- **Source code:** Browse the [native Linux source on the `linux-port` branch](https://github.com/ttmporting/DAT-Texture-Wizard/tree/linux-port).
  For source-based setup and development details, see the
  [Linux GUI guide](https://github.com/ttmporting/DAT-Texture-Wizard/blob/linux-port/README.GUI.LINUX.md).

## Credits, Copyright, and Licenses
* **png.py**  ( [Website](https://pypng.readthedocs.io/en/latest/) | [GitHub](https://github.com/drj11/pypng/) )    `- PNG codec used within the TPL codec`
    - Copyright (c) 2015 Pavel Zlatovratskii <scondo@mail.ru>
    - Copyright (c) 2006 Johann C. Rocholl <johann@browsershots.org>
    - Portions Copyright (C) 2009 David Jones <drj@pobox.com>
    - And probably portions Copyright (C) 2006 Nicko van Someren <nicko@nicko.org>
    - Original concept by Johann C. Rocholl.
    - MIT License
* **wimgt**   ( [Website](https://szs.wiimm.de/wimgt/) | [GitHub](https://github.com/Wiimm/wiimms-szs-tools) )    `- Used for CMPR (type _14) texture encoding`
    - Copyright (c) by Wiimm (2011)
    - GNU GPL v2 or later
* **pngquant** ( [Website](https://pngquant.org/) | [GitHub](https://github.com/kornelski/pngquant) )    `- Used in palette and CSP trim color generation`
    - Copyright (c) by Kornel Lesiński (2009-2018), Greg Roelofs (1997-2002), and Jef Poskanzer (1989, 1991)
    - Licensed under GPL v3 or later
* **xxHash**  ( [PyPI](https://pypi.org/project/xxhash/) | [GitHub](https://github.com/ifduyue/python-xxhash) )      `- Used for Dolphin hash generation`
    - Copyright (c) by Yue Du (2014-2020)
    - Licensed under [BSD 2-Clause License](http://opensource.org/licenses/BSD-2-Clause)
