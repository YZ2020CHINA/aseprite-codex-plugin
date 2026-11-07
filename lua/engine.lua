local M = {}
local function read(path)
  local f=assert(io.open(path,"rb")); local s=f:read("*a"); f:close(); return s
end
function M.write(path,value)
  local f=assert(io.open(path,"wb"))
  f:write(json.encode(value)); f:close()
end
function M.info(s)
  if not s then return {available=false} end
  local layers,tags,frames={},{},{}
  local function walk(list,parent)
    for _,l in ipairs(list) do
      table.insert(layers,{name=l.name,parent=parent,isGroup=l.isGroup,
        visible=l.isVisible,editable=l.isEditable,opacity=l.opacity})
      if l.isGroup then walk(l.layers,l.name) end
    end
  end
  walk(s.layers,"")
  for _,t in ipairs(s.tags) do table.insert(tags,{name=t.name,from=t.fromFrame.frameNumber,to=t.toFrame.frameNumber}) end
  for _,f in ipairs(s.frames) do table.insert(frames,{frame=f.frameNumber,duration_ms=math.floor(f.duration*1000+0.5)}) end
  return {available=true,filename=s.filename,width=s.width,height=s.height,
    colorMode=tostring(s.colorMode),layers=layers,frames=frames,tags=tags,
    modified=s.isModified}
end
local function color(hex)
  assert(type(hex)=="string" and (#hex==7 or #hex==9) and hex:match("^#%x+$"),"Use #RRGGBB or #RRGGBBAA")
  return Color{r=tonumber(hex:sub(2,3),16),g=tonumber(hex:sub(4,5),16),b=tonumber(hex:sub(6,7),16),a=#hex==9 and tonumber(hex:sub(8,9),16) or 255}
end
function M.handle(q)
  local s=app.sprite
  if q.input then s=assert(app.open(q.input),"Cannot open input"); app.sprite=s end
  local result
  if q.op=="info" then
    result=M.info(s)
    result.openDocuments={}
    for _,d in ipairs(app.sprites) do table.insert(result.openDocuments,{filename=d.filename,width=d.width,height=d.height}) end
  elseif q.op=="create" then
    local spec=q.spec
    s=Sprite(spec.width,spec.height,ColorMode.RGB)
    for i=2,#spec.durations_ms do s:newEmptyFrame() end
    for i,ms in ipairs(spec.durations_ms) do s.frames[i].duration=ms/1000 end
    local palette={}
    for symbol,hex in pairs(spec.palette) do palette[symbol]=app.pixelColor.rgba(color(hex).red,color(hex).green,color(hex).blue,color(hex).alpha) end
    for li,layerSpec in ipairs(spec.layers) do
      local layer=li==1 and s.layers[1] or s:newLayer(); layer.name=layerSpec.name
      for fi,cel in ipairs(layerSpec.frames) do
        local image=Image(s.width,s.height,ColorMode.RGB)
        for y,row in ipairs(cel.rows) do
          for x=1,#row do
            local symbol=row:sub(x,x); local px=palette[symbol]
            if px then image:drawPixel(x-1+(cel.x or 0),y-1+(cel.y or 0),px) end
          end
        end
        s:newCel(layer,fi,image)
      end
    end
    if spec.tags then
      for _,v in ipairs(spec.tags) do local t=s:newTag(v.from,v.to); t.name=v.name end
    end
    result=M.info(s)
  elseif q.op=="eval" then
    local fn=assert(load(q.code,"Codex Lua","t",_G))
    if q.transaction and app.sprite then
      local scriptError
      local ok,err=pcall(function()
        app.transaction("Codex edit",function()
          local success,value=pcall(fn)
          if not success then scriptError=tostring(value); error(scriptError) end
          result=value
        end)
      end)
      if scriptError then error(scriptError) end
      if not ok then error(tostring(err)) end
    else result=fn() end
    s=app.sprite
  elseif q.op=="export" then
    assert(s,"No active sprite")
    if q.kind=="sheet" then
      local types={horizontal=SpriteSheetType.HORIZONTAL,vertical=SpriteSheetType.VERTICAL,packed=SpriteSheetType.PACKED,rows=SpriteSheetType.ROWS,columns=SpriteSheetType.COLUMNS}
      assert(app.command.ExportSpriteSheet{ui=false,type=types[q.sheet_type or "horizontal"],textureFilename=q.output,
        dataFilename=q.data, dataFormat=SpriteSheetDataFormat.JSON_ARRAY,listLayers=true,listTags=true,
        listSlices=true,textureColumns=q.columns or 0,openGenerated=false},"ExportSpriteSheet failed")
    else
      -- Export a copy: saving must not clear an unsaved live document's dirty state.
      local copy=Sprite(s)
      if q.output:lower():match("%.png$") then
        local image=Image(copy.width,copy.height,ColorMode.RGB)
        image:drawSprite(copy,1); image:saveAs(q.output)
      else copy:saveAs(q.output) end
      copy:close(); app.sprite=s
    end
    result={output=q.output,data=q.data}
  elseif q.op=="preview" then
    assert(s,"No active sprite")
    local image=Image(s.width,s.height,ColorMode.RGB)
    image:drawSprite(s,q.frame or 1)
    if q.scale and q.scale~=1 then image:resize(s.width*q.scale,s.height*q.scale) end
    image:saveAs(q.output)
    result={output=q.output,width=image.width,height=image.height}
  elseif q.op=="snapshot" then
    assert(s,"No active sprite")
    local copy=Sprite(s)
    copy:saveAs(q.output); copy:close(); app.sprite=s
    result={output=q.output}
  else error("Unknown operation: "..tostring(q.op)) end
  if q.op~="export" and q.op~="preview" and q.op~="snapshot" and q.output then
    assert(s,"No sprite to save"); s:saveAs(q.output)
  end
  if app.isUIAvailable then app.refresh() end
  return result or {ok=true}
end
function M.run(requestPath,responsePath)
  local ok,result=pcall(function()
    local q=json.decode(read(requestPath))
    assert(not q.deadline or os.time()<=q.deadline,"Request expired; no action executed")
    return M.handle(q)
  end)
  M.write(responsePath,ok and {ok=true,result=result} or {ok=false,error=tostring(result)})
  local ready=assert(io.open(responsePath..".ready","wb")); ready:write("ready"); ready:close()
end
return M
