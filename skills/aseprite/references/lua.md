# Aseprite Lua 操作

所有片段作为 `aseprite_eval.code`，现有文件用 input，编辑用新的 .aseprite output。live 省略 input 操作活动文档。官方 API：https://aseprite.org/api/ 。本机验证版本 1.3.7，API 28。

## 笔触和像素

```lua
local s=assert(app.sprite)
local l=s.layers[1]
app.useTool{tool="line",color=Color{r=255,g=180,b=80,a=255},
  brush=Brush(1),points={Point(2,2),Point(12,8)},layer=l,frame=s.frames[1]}
return {width=s.width,height=s.height}
```

对已有 cel 做局部修改：

```lua
local s=assert(app.sprite)
local l=s.layers[1]
local cel=l:cel(1)
if not cel then cel=s:newCel(l,1,Image(s.width,s.height,ColorMode.RGB)) end
local image=Image(cel.image)
local x,y=4-cel.position.x,5-cel.position.y
if x>=0 and y>=0 and x<image.width and y<image.height then
  image:drawPixel(x,y,app.pixelColor.rgba(255,200,100,255))
  cel.image=image
end
return {position={x=cel.position.x,y=cel.position.y}}
```

## 分组、调色板与帧

```lua
local s=assert(app.sprite)
local group=s:newGroup(); group.name="角色"
local layer=s:newLayer(); layer.name="装备"; layer.parent=group
local p=Palette(4)
p:setColor(0,Color{r=0,g=0,b=0,a=0})
p:setColor(1,Color{r=30,g=25,b=45})
p:setColor(2,Color{r=180,g=100,b=160})
p:setColor(3,Color{r=255,g=225,b=180})
s:setPalette(p)
local f=s:newEmptyFrame(); f.duration=0.12
local t=s:newTag(1,#s.frames); t.name="idle"; t.aniDir=AniDir.FORWARD
return {frames=#s.frames,tag=t.name}
```

## 读回精确像素

```lua
local s=assert(app.sprite)
local img=Image(s.width,s.height,ColorMode.RGB); img:drawSprite(s,1)
local p=img:getPixel(4,5)
return {r=app.pixelColor.rgbaR(p),g=app.pixelColor.rgbaG(p),
  b=app.pixelColor.rgbaB(p),a=app.pixelColor.rgbaA(p)}
```

批处理只读片段设 read_only=true、transaction=false。新建的 RGB Image 是合成检查缓冲，不改变工程颜色模式。
