-- VolumeCalc.ms  (3ds Max 2016+)
-- Volume (m3) and surface area (m2) of selected objects.
-- World space, all modifiers applied, works with any System Unit Setup.
-- Run: Scripting > Run Script, or drag the file into a viewport.

try (destroyDialog VolumeCalcRollout) catch ()

rollout VolumeCalcRollout "Volume Calc" width:340
(
    local lastObjs = #()
    local totalVolM3 = 0.0

    button  btnCalc "Calculate selected" width:320 height:30
    listbox lbItems "Objects (double-click = select):" height:14
    group "Totals"
    (
        label lblVol  "Volume: -"       align:#left width:300
        label lblArea "Surface area: -" align:#left width:300
        label lblOpen ""                align:#left width:300
    )
    group "Board / cost"
    (
        spinner spnThick "Board thickness, mm: " range:[1,1000,28] type:#float fieldwidth:60
        label   lblBoard "Board area (V / t): -" align:#left width:300
        spinner spnPrice "Price per m3: " range:[0,10000000,0] type:#float fieldwidth:60
        label   lblCost  "Cost: -" align:#left width:300
    )

    -- meters in one system unit
    fn metersPerUnit =
    (
        local s = units.SystemScale
        case units.SystemType of
        (
            #inches:      s * 0.0254
            #feet:        s * 0.3048
            #miles:       s * 1609.344
            #millimeters: s * 0.001
            #centimeters: s * 0.01
            #meters:      s
            #kilometers:  s * 1000.0
            default:      s
        )
    )

    fn fmt v f = formattedPrint (v as float) format:f

    -- returns #(volume_units3, area_units2, isClosed, faceCount)
    fn measureNode obj =
    (
        local tm = snapshotAsMesh obj   -- world-space copy with modifiers
        local nf = tm.numfaces
        local vol = 0.0 as double
        local area = 0.0 as double
        local closed = true
        if nf > 0 do
        (
            local c = obj.center        -- local origin to keep float precision
            for i = 1 to nf do
            (
                local fc = getFace tm i
                local a = (getVert tm (fc.x as integer)) - c
                local b = (getVert tm (fc.y as integer)) - c
                local d = (getVert tm (fc.z as integer)) - c
                vol  += dot a (cross b d)                  -- signed tetrahedron volume * 6
                area += length (cross (b - a) (d - a))     -- triangle area * 2
            )
            vol  = (abs vol) / 6.0
            area = area / 2.0
            closed = (meshop.getOpenEdges tm).numberSet == 0
        )
        free tm
        #(vol, area, closed, nf)
    )

    fn updateDerived =
    (
        local t = spnThick.value / 1000.0
        lblBoard.text = "Board area (V / t): " + (fmt (totalVolM3 / t) ".2f") + " m2"
        lblCost.text = if spnPrice.value > 0 then ("Cost: " + (fmt (totalVolM3 * spnPrice.value) ".2f")) else "Cost: -"
    )

    on btnCalc pressed do
    (
        local objs = for o in selection where (superclassOf o == GeometryClass) and (canConvertTo o TriMeshGeometry) collect o
        if objs.count == 0 then
            messageBox "Select geometry objects first." title:"Volume Calc"
        else
        (
            local k  = metersPerUnit()
            local k2 = k * k
            local k3 = k2 * k
            local rows = #()
            local sumV = 0.0 as double
            local sumA = 0.0 as double
            local openCount = 0
            lastObjs = #()
            format "\n==== Volume Calc ====\n"
            for o in objs do
            (
                local r = measureNode o
                if r[4] > 0 do
                (
                    local v = r[1] * k3
                    local a = r[2] * k2
                    sumV += v
                    sumA += a
                    local flag = ""
                    if not r[3] do (flag = "  [OPEN]"; openCount += 1)
                    local txt = o.name + ":  " + (fmt v ".4f") + " m3" + flag
                    append rows txt
                    append lastObjs o
                    format "%\n" txt
                )
            )
            lbItems.items = rows
            totalVolM3 = sumV as float
            lblVol.text  = "Volume: " + (fmt sumV ".4f") + " m3  (" + rows.count as string + " obj)"
            lblArea.text = "Surface area: " + (fmt sumA ".2f") + " m2"
            lblOpen.text = if openCount > 0 then (openCount as string + " open mesh(es): volume unreliable") else "All meshes closed"
            updateDerived()
            format "TOTAL: % m3, surface % m2\n" (fmt sumV ".4f") (fmt sumA ".2f")
        )
    )

    on lbItems doubleClicked i do
        if i > 0 and i <= lastObjs.count and isValidNode lastObjs[i] do select lastObjs[i]

    on spnThick changed v do updateDerived()
    on spnPrice changed v do updateDerived()
)

createDialog VolumeCalcRollout
