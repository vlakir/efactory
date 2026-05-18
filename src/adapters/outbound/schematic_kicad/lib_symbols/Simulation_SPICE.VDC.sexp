		(symbol "Simulation_SPICE:VDC"
					(pin_numbers
						(hide yes)
					)
					(pin_names
						(offset 0.254)
					)
					(exclude_from_sim no)
					(in_bom yes)
					(on_board yes)
					(property "Reference" "V" (at 0 3.81 0))
					(property "Value" "VDC" (at 0 -3.81 0))
					(property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
					(property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
					(property "Sim.Pins" "1=+ 2=-" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
					(property "Sim.Type" "V" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
					(property "Sim.Device" "SPICE" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
					(property "Sim.Library" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
					(property "Sim.Params" "dc=1 ac=1" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
					(symbol "VDC_0_1"
						(circle (center 0 0) (radius 1.27) (stroke (width 0) (type default)) (fill (type none)))
					)
					(symbol "VDC_1_1"
						(pin passive line (at 0 2.54 270) (length 1.27) (name "+" (effects (font (size 1 1)))) (number "1" (effects (font (size 1 1)))))
						(pin passive line (at 0 -2.54 90) (length 1.27) (name "-" (effects (font (size 1 1)))) (number "2" (effects (font (size 1 1)))))
					)
				)
