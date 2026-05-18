		(symbol "Valve:EC92"
			(pin_names
				(offset 0)
			)
			(exclude_from_sim no)
			(in_bom yes)
			(on_board yes)
			(in_pos_files yes)
			(duplicate_pin_numbers_are_jumpers no)
			(property "Reference" "U"
				(at 3.048 7.874 0)
				(show_name no)
				(do_not_autoplace no)
				(effects
					(font
						(size 1.27 1.27)
					)
				)
			)
			(property "Value" "EC92"
				(at 4.318 -8.128 0)
				(show_name no)
				(do_not_autoplace no)
				(effects
					(font
						(size 1.27 1.27)
					)
				)
			)
			(property "Footprint" "Valve:Valve_Mini_P"
				(at 6.858 -9.652 0)
				(show_name no)
				(do_not_autoplace no)
				(hide yes)
				(effects
					(font
						(size 1.27 1.27)
					)
				)
			)
			(property "Datasheet" "http://www.r-type.org/pdfs/ec92.pdf"
				(at 0 0 0)
				(show_name no)
				(do_not_autoplace no)
				(hide yes)
				(effects
					(font
						(size 1.27 1.27)
					)
				)
			)
			(property "Description" "single triode"
				(at 0 0 0)
				(show_name no)
				(do_not_autoplace no)
				(hide yes)
				(effects
					(font
						(size 1.27 1.27)
					)
				)
			)
			(property "ki_locked" ""
				(at 0 0 0)
				(show_name no)
				(do_not_autoplace no)
				(effects
					(font
						(size 1.27 1.27)
					)
				)
			)
			(property "ki_keywords" "triode valve"
				(at 0 0 0)
				(show_name no)
				(do_not_autoplace no)
				(hide yes)
				(effects
					(font
						(size 1.27 1.27)
					)
				)
			)
			(property "ki_fp_filters" "VALVE*MINI*P*"
				(at 0 0 0)
				(show_name no)
				(do_not_autoplace no)
				(hide yes)
				(effects
					(font
						(size 1.27 1.27)
					)
				)
			)
			(symbol "EC92_0_1"
				(polyline
					(pts
						(xy -5.08 2.54) (xy -5.08 -2.54) (xy -5.08 -2.54)
					)
					(stroke
						(width 0)
						(type default)
					)
					(fill
						(type none)
					)
				)
				(arc
					(start -5.08 2.54)
					(mid 0 7.5979)
					(end 5.08 2.54)
					(stroke
						(width 0)
						(type default)
					)
					(fill
						(type none)
					)
				)
				(arc
					(start 5.08 -2.54)
					(mid 0 -7.5979)
					(end -5.08 -2.54)
					(stroke
						(width 0)
						(type default)
					)
					(fill
						(type none)
					)
				)
				(polyline
					(pts
						(xy 5.08 2.54) (xy 5.08 -2.54)
					)
					(stroke
						(width 0)
						(type default)
					)
					(fill
						(type none)
					)
				)
			)
			(symbol "EC92_1_0"
				(polyline
					(pts
						(xy -2.54 -5.08) (xy -2.54 -7.62)
					)
					(stroke
						(width 0)
						(type default)
					)
					(fill
						(type none)
					)
				)
				(polyline
					(pts
						(xy -1.905 0) (xy -3.175 0)
					)
					(stroke
						(width 0.1524)
						(type default)
					)
					(fill
						(type none)
					)
				)
				(polyline
					(pts
						(xy -0.635 0) (xy 0.635 0)
					)
					(stroke
						(width 0.1524)
						(type default)
					)
					(fill
						(type none)
					)
				)
				(polyline
					(pts
						(xy 0 5.08) (xy 0 7.62)
					)
					(stroke
						(width 0)
						(type default)
					)
					(fill
						(type none)
					)
				)
				(polyline
					(pts
						(xy 1.905 0) (xy 3.175 0)
					)
					(stroke
						(width 0.1524)
						(type default)
					)
					(fill
						(type none)
					)
				)
			)
			(symbol "EC92_1_1"
				(polyline
					(pts
						(xy -5.08 0) (xy -3.175 0)
					)
					(stroke
						(width 0)
						(type default)
					)
					(fill
						(type none)
					)
				)
				(polyline
					(pts
						(xy -2.54 5.08) (xy 2.54 5.08) (xy 2.54 5.08)
					)
					(stroke
						(width 0.254)
						(type default)
					)
					(fill
						(type none)
					)
				)
				(arc
					(start -2.54 -5.08)
					(mid 0 -3.0968)
					(end 2.54 -5.08)
					(stroke
						(width 0.254)
						(type default)
					)
					(fill
						(type none)
					)
				)
				(pin output line
					(at 0 10.16 270)
					(length 2.54)
					(name "A"
						(effects
							(font
								(size 1.27 1.27)
							)
						)
					)
					(number "1"
						(effects
							(font
								(size 1.27 1.27)
							)
						)
					)
				)
				(pin input line
					(at -7.62 0 0)
					(length 2.54)
					(name "G"
						(effects
							(font
								(size 1.27 1.27)
							)
						)
					)
					(number "6"
						(effects
							(font
								(size 1.27 1.27)
							)
						)
					)
				)
				(pin bidirectional line
					(at -2.54 -10.16 90)
					(length 2.54)
					(name "K"
						(effects
							(font
								(size 1.27 1.27)
							)
						)
					)
					(number "7"
						(effects
							(font
								(size 1.27 1.27)
							)
						)
					)
				)
			)
			(embedded_fonts no)
		)