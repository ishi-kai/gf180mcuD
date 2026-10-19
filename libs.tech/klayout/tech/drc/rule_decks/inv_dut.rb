# frozen_string_literal: true

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# RISC-V Day MPW inverter DUT frame checks.
#
# Compares the DUT layout against the reference frame (inv_dut/inverter_base.gds):
#   INV.PRB.1 : PR_BNDRY must be identical to the reference (center (0,0), W 20um x H 50um).
#   INV.BND.1 : Nothing may be drawn outside the reference PR_BNDRY area.
#   INV.M1.1  : Reference Metal1 (VDD/VSS/A/Q pins) must not be removed or modified.
#   INV.LBL.1 : Reference Metal1 labels (VDD/VSS/A/Q) must exist unchanged (text and position).
#   INV.LBL.2 : No additional Metal1 labels are allowed.
#
# This deck is not part of "all". Enable it with: -rd decks=all,-density,inv_dut
# The reference GDS can be overridden with: -rd inv_dut_base=<path>

GF180_DRC_REGISTRY.register(
  id: File.basename(__FILE__, File.extname(__FILE__)),
  path: __FILE__,
  priority: 0,
  tags: %w[inv_dut]
) do
  ref_path = $inv_dut_base || File.join(__dir__, '..', 'inv_dut', 'inverter_base.gds')
  logger.info("Reference frame for inv_dut checks: #{ref_path}")
  raise ArgumentError, "inv_dut reference GDS not found: #{ref_path}" unless File.exist?(ref_path)

  ref_layout = RBA::Layout.new
  ref_layout.read(ref_path)
  ref_top = ref_layout.top_cell

  dut_layout = source.layout
  dut_top = source.cell_obj
  # Reference coordinates are converted into the DUT database unit
  ref_trans = RBA::ICplxTrans.new(ref_layout.dbu / dut_layout.dbu)

  ref_region = lambda do |lnum, dtype|
    li = ref_layout.find_layer(lnum, dtype)
    li ? RBA::Region.new(ref_top.begin_shapes_rec(li)).transformed(ref_trans) : RBA::Region.new
  end
  ref_texts = lambda do |lnum, dtype|
    li = ref_layout.find_layer(lnum, dtype)
    li ? RBA::Texts.new(ref_top.begin_shapes_rec(li)).transformed(ref_trans) : RBA::Texts.new
  end
  dut_region = lambda do |lnum, dtype|
    li = dut_layout.find_layer(lnum, dtype)
    li ? RBA::Region.new(dut_top.begin_shapes_rec(li)) : RBA::Region.new
  end
  dut_texts = lambda do |lnum, dtype|
    li = dut_layout.find_layer(lnum, dtype)
    li ? RBA::Texts.new(dut_top.begin_shapes_rec(li)) : RBA::Texts.new
  end
  # Text markers are drawn as 0.2um boxes so that they show up in the report
  text_marker = ->(texts) { texts.polygons((0.1 / dut_layout.dbu).round) }
  out = ->(data, rule, desc) { DRC::DRCLayer.new(drc, data).output(rule, desc) }

  ref_prb = ref_region.call(0, 0).merged

  # Rule INV.PRB.1: PR_BNDRY must be identical to the reference frame.
  logger.info('Executing rule INV.PRB.1')
  prb_diff = dut_region.call(0, 0).merged ^ ref_prb
  unless prb_diff.is_empty?
    out.call(prb_diff, 'INV.PRB.1',
             'INV.PRB.1 : PR_BNDRY (0/0) must not be changed (center x=0,y=0, height 50um x width 20um).')
  end

  # Rule INV.BND.1: Nothing may be drawn outside the PR_BNDRY area.
  logger.info('Executing rule INV.BND.1')
  outside = RBA::Region.new
  outside_texts = RBA::Texts.new
  dut_layout.layer_indexes.each do |li|
    outside += RBA::Region.new(dut_top.begin_shapes_rec(li)) - ref_prb
    outside_texts += RBA::Texts.new(dut_top.begin_shapes_rec(li)).not_interacting(ref_prb)
  end
  outside += text_marker.call(outside_texts)
  unless outside.is_empty?
    out.call(outside, 'INV.BND.1',
             'INV.BND.1 : No shapes or labels are allowed outside the PR_BNDRY area.')
  end

  # Rule INV.M1.1: Reference Metal1 (VDD/VSS/A/Q pins) must remain unchanged.
  logger.info('Executing rule INV.M1.1')
  m1_missing = ref_region.call(34, 0) - dut_region.call(34, 0)
  unless m1_missing.is_empty?
    out.call(m1_missing, 'INV.M1.1',
             'INV.M1.1 : Metal1 of the VDD/VSS/A/Q pins (from inverter_base.gds) must not be removed or modified.')
  end

  # Rules INV.LBL.1/2: Metal1 labels must be exactly the reference labels.
  logger.info('Executing rules INV.LBL.1 and INV.LBL.2')
  remaining = dut_texts.call(34, 10).each.to_a
  missing = RBA::Texts.new
  ref_texts.call(34, 10).each do |rt|
    idx = remaining.index { |t| t.string == rt.string && t.trans.disp == rt.trans.disp }
    if idx
      remaining.delete_at(idx)
    else
      missing.insert(rt)
    end
  end
  unless missing.is_empty?
    out.call(text_marker.call(missing), 'INV.LBL.1',
             'INV.LBL.1 : Metal1 labels VDD/VSS/A/Q (34/10) must not be removed, renamed or moved.')
  end
  extra = RBA::Texts.new
  remaining.each { |t| extra.insert(t) }
  unless extra.is_empty?
    out.call(text_marker.call(extra), 'INV.LBL.2',
             'INV.LBL.2 : Additional Metal1 labels (34/10) are not allowed.')
  end
end
