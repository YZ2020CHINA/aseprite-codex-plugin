function init(plugin)
  plugin:newCommand{id="CodexAsepriteConnect",title="Connect to Codex",group="file_scripts",
    onclick=function() dofile(app.fs.joinPath(plugin.path,"bridge.lua")) end}
end
function exit(plugin)
  if _G.codexAsepriteBridge then _G.codexAsepriteBridge:stop(); _G.codexAsepriteBridge=nil end
end
