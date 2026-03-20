#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# === This file is part of Calamares - <http://github.com/calamares> ===
#
#   Copyright 2014 - 2019, Philip Müller <philm@manjaro.org>
#   Copyright 2016, Artoo <artoo@manjaro.org>
#
#   Calamares is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   Calamares is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with Calamares. If not, see <http://www.gnu.org/licenses/>.

import libcalamares
import subprocess
from shutil import copy2, copytree
from os.path import join, exists
from libcalamares.utils import target_env_call, target_env_process_output


class ConfigController:
    def __init__(self):
        self.__root = libcalamares.globalstorage.value("rootMountPoint")
        self.__keyrings = libcalamares.job.configuration.get('keyrings', [])

    @property
    def root(self):
        return self.__root

    @property
    def keyrings(self):
        return self.__keyrings

    def init_keyring(self):
        target_env_call(["pacman-key", "--init"])

    def populate_keyring(self):
        target_env_call(["pacman-key", "--populate"])

    def terminate(self, proc):
        target_env_call(['killall', '-9', proc])

    def copy_file(self, file):
        if exists("/" + file):
            copy2("/" + file, join(self.root, file))

    def copy_folder(self, source, target):
        if exists("/" + source):
            copytree("/" + source, join(self.root, target),
                     symlinks=True, dirs_exist_ok=True)

    def find_xdg_directory(self, user, type):
        output = []
        target_env_process_output(
            ["su", "-lT", user, "xdg-user-dir", type], output
        )
        return output[0].strip()

    def mark_orphans_as_explicit(self) -> None:
        libcalamares.utils.debug(
            "Marking orphaned packages as explicit in installed system..."
        )
        target_env_call([
            "sh", "-c",
            "orphans=$(pacman -Qdtq); "
            "if [ -n \"$orphans\" ]; then pacman -D --asexplicit $orphans; fi"
        ])
        libcalamares.utils.debug("Package marking completed.")

    # ---------------------------------------------------------
    # MICROCODE FIX
    # ---------------------------------------------------------
    def handle_ucode(self):
        vendor = subprocess.getoutput(
            "grep -m1 vendor_id /proc/cpuinfo | awk '{print $3}'"
        ).strip()

        libcalamares.utils.debug(f"Detected CPU vendor: {vendor}")

        if vendor == "AuthenticAMD":
            target_env_call([
                "sh", "-c",
                "pacman -Q intel-ucode && pacman -Rns --noconfirm intel-ucode || true"
            ])
        elif vendor == "GenuineIntel":
            target_env_call([
                "sh", "-c",
                "pacman -Q amd-ucode && pacman -Rns --noconfirm amd-ucode || true"
            ])

    # ---------------------------------------------------------
    # BTRFS DETECTION
    # ---------------------------------------------------------
    def is_btrfs_root(self) -> bool:
        partitions = libcalamares.globalstorage.value("partitions")

        if not partitions:
            return False

        for partition in partitions:
            if partition.get("mountPoint") == "/":
                return partition.get("fs") == "btrfs"

        return False

    # ---------------------------------------------------------
    # DETECCIÓN DE BIOS / UEFI
    # ---------------------------------------------------------
    def is_bios(self) -> bool:
        """ Retorna True si el sistema es BIOS Legacy, False si es UEFI """
        return not exists("/sys/firmware/efi")

    # ---------------------------------------------------------
    # LIMINE FIX (Solo para BIOS)
    # ---------------------------------------------------------
    def fix_limine(self):
        # Solo ejecutar si es BIOS Legacy
        if self.is_bios():
            libcalamares.utils.debug("Sistema BIOS detectado. Aplicando fix de Limine...")
            
            # 1. Eliminar el antiguo
            target_env_call([
                "sh", "-c",
                "pacman -R --noconfirm limine-entry-tool || true"
            ])

            # 2. Instalar el hook con elección automática de proveedor (Java)
            target_env_call([
                "sh", "-c",
                "echo 1 | pacman -S --noconfirm --needed limine-mkinitcpio-hook"
            ])
            
            # 3. Regenerar initramfs para disparar la creación del limine.conf
            libcalamares.utils.debug("Generando archivos de arranque para BIOS...")
            target_env_call(["mkinitcpio", "-P"])
        else:
            libcalamares.utils.debug("Sistema UEFI detectado. Saltando fix de Limine BIOS.")

    # ---------------------------------------------------------
    # MAIN RUN
    # ---------------------------------------------------------
    def run(self) -> None:
        # self.init_keyring()
        # self.populate_keyring()

        self.fix_limine()

        # --- Microcode ---
        # self.handle_ucode()

        # Kill gpg-agent
        # self.terminate('gpg-agent')

        # Mark orphan packages
        # self.mark_orphans_as_explicit()

        # --- Snapper config ---
        if self.is_btrfs_root():
            libcalamares.utils.debug("Btrfs detected. Configuring Snapper...")

            if exists(join(self.root, "usr/bin/snapper")):
                target_env_call([
                    "snapper", "--no-dbus", "-c", "root", "create-config", "/"
                ])
                target_env_call(["systemctl", "enable", "snapper-timeline.timer"])
                target_env_call(["systemctl", "enable", "snapper-cleanup.timer"])

                if exists(join(self.root, "usr/bin/grub-btrfsd")):
                    target_env_call(["systemctl", "enable", "grub-btrfsd.service"])
        else:
            libcalamares.utils.debug(
                "Non-Btrfs filesystem detected. Removing Snapper stack..."
            )
            target_env_call([
                "sh", "-c",
                "pacman -Rns --noconfirm snapper snap-pac grub-btrfs inotify-tools 2>/dev/null || true"
            ])

        return None


def run():
    config = ConfigController()
    return config.run()
