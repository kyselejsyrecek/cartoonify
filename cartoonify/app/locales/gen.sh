#!/usr/bin/env bash

ask() {
  while true; do
      read -p "$1 " yn
      case $yn in
          [Yy]* ) return 0;;
          [Nn]* ) return 1;;
          * ) echo "Please answer yes or no.";;
      esac
  done
}

if ask "Do you wish to regenerate cartoonify.pot file?"; then
  xgettext -d base -o cartoonify.pot ../gui/gui.py
fi

if ask "Do you wish to regenerate cartoonify.po files form cartoonify.pot?"; then
  cp cartoonify.pot */LC_MESSAGES/cartoonify.po
fi

if ask "Do you wish to recompile cartoonify.mo files?"; then
  for lang in *; do
    [ ! -d $lang ] && continue
    msgfmt -o $lang/LC_MESSAGES/cartoonify.mo $lang/LC_MESSAGES/cartoonify.po
  done
fi

echo "Done."