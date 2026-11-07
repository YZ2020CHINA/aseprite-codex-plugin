-- Installed as a menu command. The generated settings file is specific to this user.
local settings=dofile(app.fs.joinPath(app.fs.filePath(debug.getinfo(1,"S").source:sub(2)),"settings.lua"))
local engine=dofile(settings.engine)
if _G.codexAsepriteBridge then _G.codexAsepriteBridge:stop() end
local function heartbeat()
  local p=app.fs.joinPath(settings.queue,"heartbeat.json")
  engine.write(p,{version=tostring(app.version),updated=os.time(),ui=app.isUIAvailable})
end
local processed={}
local timer
timer=Timer{interval=0.2,ontick=function()
  local ok,err=pcall(function()
  heartbeat()
  local pending={}
  for _,name in ipairs(app.fs.listFiles(settings.queue)) do
    local p=app.fs.joinPath(settings.queue,name)
    if p:match("%.request%.json$") and not processed[p] then table.insert(pending,p) end
  end
  table.sort(pending)
  for _,p in ipairs(pending) do
    processed[p]=true
    engine.run(p,p:gsub("%.request%.json$",".response.json"))
  end
  for p,_ in pairs(processed) do if not app.fs.isFile(p) then processed[p]=nil end end
  end)
  if not ok then timer:stop(); print("Codex bridge stopped: "..tostring(err)) end
end}
_G.codexAsepriteBridge=timer
heartbeat(); timer:start()
