-- Give every table proportional, wrapping column widths.
--
-- pandoc renders pipe tables whose delimiter rows carry no width hints as
-- natural-width (l/c/r) columns, which do NOT wrap -- so long prose cells
-- spill past the page margin. This filter assigns each column a relative
-- width proportional to its widest cell (capped so one long column can't
-- starve the others), which makes pandoc emit wrapping p{} columns.

local stringify = pandoc.utils.stringify

local function scan(rows, maxlen)
  for _, row in ipairs(rows) do
    for i, cell in ipairs(row.cells) do
      local s = stringify(cell.contents)
      local len = utf8.len(s) or #s
      if len > (maxlen[i] or 0) then maxlen[i] = len end
    end
  end
end

function Table(tbl)
  local ncol = #tbl.colspecs
  if ncol == 0 then return nil end

  local maxlen = {}
  for i = 1, ncol do maxlen[i] = 1 end
  if tbl.head then scan(tbl.head.rows, maxlen) end
  for _, b in ipairs(tbl.bodies) do scan(b.body, maxlen) end

  -- cap a single very long column so it doesn't crowd out the rest
  local CAP = 55
  for i = 1, ncol do if maxlen[i] > CAP then maxlen[i] = CAP end end

  local total = 0
  for i = 1, ncol do total = total + maxlen[i] end
  for i = 1, ncol do
    tbl.colspecs[i][2] = maxlen[i] / total
  end
  return tbl
end
