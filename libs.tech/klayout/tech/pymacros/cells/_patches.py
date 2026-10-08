# Copyright 2025 GlobalFoundries PDK Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# ==============================================================================
# ---------------- Patches for compatibility with gdsfactory v9 ----------------
# ==============================================================================

def _patch_class_attr(cls, name, attr, force=False):
    """
    Add or replace an attribute (method or property) on a class.

    Args:
        cls: The class to patch.
        name: The name of the attribute to add.
        attr: The method or property object.
        force: If True, will override existing attributes.
    """
    if not hasattr(cls, name) or force:
        setattr(cls, name, attr)
    else:
        print(f"[patch_class_attr] Skipped: '{cls.__name__}.{name}' already exists.")


def patch_legacy_classes():
    import gdsfactory as gf
    from importlib.util import find_spec
    from typing import Optional

    #
    # Replacement for gdsfactory.Component.add_array() method
    #

    # noinspection PyPep8Naming
    def __gf__Component__add_array(
        self: gf.Component,
        component: gf.Component,
        columns: int = 2,
        rows: int = 2,
        spacing: tuple[float, float] = (100, 100),
        alias: Optional[str] = None
    ) -> gf.ComponentReference:
        column_pitch = spacing[0]
        row_pitch = spacing[1]
        ref = self.add_ref(
            component=component,
            name=alias,
            columns=columns,
            rows=rows,
            column_pitch=column_pitch,
            row_pitch=row_pitch
        )
        return ref


    # noinspection PyPep8Naming
    def __gf__component_layout___GeometryHelper__size(self):  # gf.component_layout._GeometryHelper
        return self.xsize, self.ysize


    _patch_class_attr(gf.Component, 'add_array', __gf__Component__add_array)
    _patch_class_attr(gf.Component, 'size', property(__gf__component_layout___GeometryHelper__size))
    _patch_class_attr(gf.ComponentReference, 'size', property(__gf__component_layout___GeometryHelper__size))

    # class gdsfactory.geometry.boolean (v7) now resides under gdsfactory.boolean (v9)
    if find_spec('gdsfactory.geometry') is None:
        class DummyNamespace:
            pass
        gf__geometry = DummyNamespace()
        gf__geometry.boolean = gf.boolean
        gf.geometry = gf__geometry


    # gf.Component("nfet_dev") for example would yield the error below, e.g. when changing PCell parameters
    #
    #ERROR: ValueError: Cellname nfet_dev already exists. Please make sure the cellname is unique or pass `allow_duplicate` when creating the library in PCellDeclaration.produce
    #  /usr/local/lib/python3.12/dist-packages/kfactory/layout.py:1209
    #  /usr/local/lib/python3.12/dist-packages/kfactory/kcell.py:594
    #  /usr/local/lib/python3.12/dist-packages/kfactory/kcell.py:2563

    import klayout.db as kdb
    import kfactory.layout
    original_method = kfactory.layout.KCLayout.create_cell

    # noinspection PyPep8Naming
    def __kfactory__layout__KCLayout_create_cell(
        self,
        name: str,
        *args: str,
        allow_duplicate: bool = True,
    ) -> kdb.Cell:
        return original_method(self, name, *args, allow_duplicate=allow_duplicate)

    kfactory.layout.KCLayout.create_cell = __kfactory__layout__KCLayout_create_cell

    #
    # Emulate the gdsfactory v7 get_polygons(by_spec=...) API:
    #   by_spec=True          -> {(layer, datatype): [ndarray of (x_um, y_um), ...]}
    #   by_spec=(l, d)        -> [ndarray of (x_um, y_um), ...] for that layer only
    # Modern calls (no by_spec) pass through unchanged. Also provided on
    # ComponentReference/Instance (v7 allowed it on references; coordinates are
    # returned in the parent frame, i.e. with the instance transform applied).
    #
    import numpy as _np

    _orig_get_polygons = gf.Component.get_polygons

    def __v7_polys_um(polys, dbu):
        return [
            _np.array([(pt.x * dbu, pt.y * dbu) for pt in poly.each_point_hull()])
            for poly in polys
        ]

    # noinspection PyPep8Naming
    def __gf__Component__get_polygons_v7compat(self, by_spec=False, **kwargs):
        if by_spec is False or by_spec is None:
            return _orig_get_polygons(self, **kwargs)
        dbu = self.kcl.dbu
        per_spec = _orig_get_polygons(self, by="tuple")
        if by_spec is True:
            return {
                spec: __v7_polys_um(polys, dbu) for spec, polys in per_spec.items()
            }
        return __v7_polys_um(per_spec.get(tuple(by_spec), []), dbu)

    # noinspection PyPep8Naming
    def __gf__ComponentReference__get_polygons_v7compat(self, by_spec=False, **kwargs):
        cell = self.cell
        ly = cell.kcl.layout
        dbu = ly.dbu
        inst_trans = self.dcplx_trans

        def polys_for(spec):
            li = ly.layer(kdb.LayerInfo(spec[0], spec[1]))
            out = []
            it = cell.kdb_cell.begin_shapes_rec(li)
            while not it.at_end():
                sh = it.shape()
                if sh.is_polygon() or sh.is_box() or sh.is_path():
                    dp = sh.polygon.transformed(it.trans()).to_dtype(dbu)
                    dp = dp.transformed(inst_trans)
                    out.append(
                        _np.array([(pt.x, pt.y) for pt in dp.each_point_hull()])
                    )
                it.next()
            return out

        if by_spec is True:
            result = {}
            for li in ly.layer_indexes():
                info = ly.get_info(li)
                polys = polys_for((info.layer, info.datatype))
                if polys:
                    result[(info.layer, info.datatype)] = polys
            return result
        return polys_for(tuple(by_spec))

    _patch_class_attr(
        gf.Component, "get_polygons", __gf__Component__get_polygons_v7compat, force=True
    )
    _patch_class_attr(
        gf.ComponentReference,
        "get_polygons",
        __gf__ComponentReference__get_polygons_v7compat,
        force=True,
    )

    #
    # Emulate the gdsfactory v7 ComponentReference.connect(port, destination=...)
    # keyword. v7 did not enforce port width/layer/type compatibility, so v7-style
    # calls also relax those checks (kfactory >= 2 raises on mismatch by default).
    # Modern-style calls pass through unchanged.
    #
    _orig_connect = gf.ComponentReference.connect

    # noinspection PyPep8Naming
    def __gf__ComponentReference__connect_v7compat(
        self, port, *args, destination=None, **kwargs
    ):
        if destination is not None:
            kwargs.setdefault("allow_width_mismatch", True)
            kwargs.setdefault("allow_layer_mismatch", True)
            kwargs.setdefault("allow_type_mismatch", True)
            return _orig_connect(self, port, destination, **kwargs)
        return _orig_connect(self, port, *args, **kwargs)

    _patch_class_attr(
        gf.ComponentReference,
        "connect",
        __gf__ComponentReference__connect_v7compat,
        force=True,
    )

    #
    # The container always exports PDK=<name> (e.g. gf180mcuD). gdsfactory maps
    # $PDK into CONF.pdk, so get_active_pdk() skips the clean "no PDK -> ValueError"
    # path and tries to import a gdsfactory PDK plugin named "gf180mcuD". No such
    # plugin exists (KLayout-native pcells), so it raises ModuleNotFoundError and
    # the tech aborts with "no PDK info found for tech". Fall back to the generic
    # PDK on any failure; a real PDK the user activated beforehand is not overridden.
    #
    try:
        gf.get_active_pdk()
    except Exception:
        gf.gpdk.PDK.activate()