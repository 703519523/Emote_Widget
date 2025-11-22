class EmoteDevice
{
    constructor() {
        if (this.initRenderCanvas()
            && this.initWebGL()
            && this.initGLEnv()
            && this.initRenderTexture()
            && this.initEmoteDevice()
            && this.initMembers())
            this.initialized = true;
        else
            this.initialized = false;
    }

    initRenderCanvas() {
        this.renderCanvas = EmotePlayer.renderCanvas;
        if (this.renderCanvas == null) {
            alert("Unable to initialize Emote Device. Set render canvas first.");
            return false;
        }
        this.width = this.renderCanvas.width;
        this.height = this.renderCanvas.height;
        return true;
    }

    initWebGL() {
        this.gl = null;
        try {
            GL.init();
            const contextAttributes = {
                antialias: true,
                alpha: true,
                depth: false,
                stencil: true,
            };
            this.hgl = GL.createContext(this.renderCanvas, contextAttributes);
            GL.makeContextCurrent(this.hgl);
            this.gl = GL.contexts[this.hgl].GLctx;
        } catch(e) {
        }

        if (! this.gl) {
            alert("Unable to initialize WebGL. Your browser may not support it.");
            return false;
        }
        return true;
    }

    createMat4() {
        const out = new Float32Array(16);
        out[0] = 1;
        out[1] = 0;
        out[2] = 0;
        out[3] = 0;
        out[4] = 0;
        out[5] = 1;
        out[6] = 0;
        out[7] = 0;
        out[8] = 0;
        out[9] = 0;
        out[10] = 1;
        out[11] = 0;
        out[12] = 0;
        out[13] = 0;
        out[14] = 0;
        out[15] = 1;
        return out;
    }

    initGLEnv() {
        if (! this.gl)
            return false;

        const vs_src = `
        precision mediump float;
        attribute vec4 a_pos;
        attribute vec2 a_texCoord;
        uniform vec2 u_scrSize;
        uniform vec2 u_texSize;
        uniform mat4 u_mvpMat;
        varying vec2 v_texCoord;

        void main()
        {
	        vec4 tmp;
	        tmp = u_mvpMat * a_pos;
	        gl_Position.x = (tmp.x *  2.0) / u_scrSize.x;
	        gl_Position.y = (tmp.y * -2.0) / u_scrSize.y;
	        gl_Position.z = a_pos.z;
	        gl_Position.w = a_pos.w;
	        v_texCoord.x = a_texCoord.x / u_texSize.x;
	        v_texCoord.y = a_texCoord.y / u_texSize.y;
        }`;
        const fs_src = `
        precision mediump float;
        varying vec2 v_texCoord;
        uniform sampler2D u_texUnitId;
        uniform vec4 u_texColor;
        
        void main()
        {
	        vec4 tmp;
	        tmp = texture2D(u_texUnitId, v_texCoord);
            tmp *= u_texColor;
            tmp.rgb *= tmp.a;
            if (tmp.a <= 0.003) {
                discard;
            }
	        gl_FragColor = tmp;
        }`;
        const gl = this.gl;
        this.shader_program = gl.createProgram();
        const vs = gl.createShader(gl.VERTEX_SHADER);
        const fs = gl.createShader(gl.FRAGMENT_SHADER);
        gl.shaderSource(vs, vs_src);
        gl.shaderSource(fs, fs_src);
        gl.compileShader(vs);
        gl.compileShader(fs);
        gl.attachShader(this.shader_program, vs);
        gl.attachShader(this.shader_program, fs);
        gl.linkProgram(this.shader_program);
        this.aLoc = [];
        this.uLoc = [];
        this.aLoc[0] = gl.getAttribLocation(this.shader_program, "a_pos");
        this.aLoc[1] = gl.getAttribLocation(this.shader_program, "a_texCoord");
        this.uLoc[0] = gl.getUniformLocation(this.shader_program, "u_scrSize");
        this.uLoc[1] = gl.getUniformLocation(this.shader_program, "u_texSize");
        this.uLoc[2] = gl.getUniformLocation(this.shader_program, "u_mvpMat");
        this.uLoc[3] = gl.getUniformLocation(this.shader_program, "u_texUnitId");
        this.uLoc[4] = gl.getUniformLocation(this.shader_program, "u_texColor");
        gl.enableVertexAttribArray(this.aLoc[0]);
        gl.enableVertexAttribArray(this.aLoc[1]);

        this.pMatrix = this.createMat4();
        this.vertexPositionBuffer = gl.createBuffer();
        gl.bindBuffer(gl.ARRAY_BUFFER, this.vertexPositionBuffer);
        const data = [ 
                -(this.width/2), -(this.height/2), 0,
            (this.width/2), -(this.height/2), 0,
            (this.width/2),  (this.height/2), 0,
                -(this.width/2),  (this.height/2), 0
        ];
        gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(data), gl.STATIC_DRAW);
        gl.vertexAttribPointer(this.aLoc[0], 3, gl.FLOAT, false, 0, 0);
        
        this.coordBuffer = gl.createBuffer();
        gl.bindBuffer(gl.ARRAY_BUFFER, this.coordBuffer);
        const textureCoords = [
            0, this.height,
            this.width, this.height,
            this.width,          0,
            0,          0,
        ];
        gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(textureCoords), gl.STATIC_DRAW);
        gl.vertexAttribPointer(this.aLoc[1], 2, gl.FLOAT, false, 0, 0);
        
        this.vertexIndexBuffer = gl.createBuffer();
        gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, this.vertexIndexBuffer);
        const indices = [
            0,  1,  2,
            0,  2 , 3
        ];
        gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, new Uint16Array(indices), gl.STATIC_DRAW);
        gl.disable(gl.DEPTH_TEST);           // Enable depth testing

        return true;
    }

    initRenderTexture() {
      // レンダーテクスチャの設定
        const gl = this.gl;
        this.renderTexture = EmoteDevice_CreateEmoteTexture2(this.width, this.height);
        return true;
    }

    initEmoteDevice() {
        this.device = EmoteDevice_Initialize();
        EmoteDevice_ChangeFrameBufferSize(this.width, this.height);
        return true;
    }

    initMembers() {
        this.playerList = [];
        this.animating = false;
        this.date = new Date();
        return true;
    }
    
    // --- 修改开始 ---
    readPixelAlpha(x, y) {
        if (!this.gl || !this.renderTexture) {
            return 0;
        }
        const gl = this.gl;

        // 1. 从 C++ 核心获取原始的、渲染好的纹理
        const sourceTexture = EmoteDevice_GetEmoteTexture2Tex(this.renderTexture);
        if (!sourceTexture) {
            return 0;
        }

        // 2. 创建一个临时的帧缓冲对象 (FBO)
        const tempFbo = gl.createFramebuffer();

        // 3. 绑定 FBO 并将源纹理直接附加到它上面
        gl.bindFramebuffer(gl.FRAMEBUFFER, tempFbo);
        gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, sourceTexture, 0);

        // 4. 检查 FBO 状态，确保它可以被读取
        const status = gl.checkFramebufferStatus(gl.FRAMEBUFFER);
        if (status !== gl.FRAMEBUFFER_COMPLETE) {
            // 如果不完整，清理并返回
            gl.bindFramebuffer(gl.FRAMEBUFFER, null);
            gl.deleteFramebuffer(tempFbo);
            return 0;
        }

        // 5. 读取单个像素
        const pixelData = new Uint8Array(4);
        // WebGL Y坐标系的原点在左下角，所以 Y 轴需要翻转
        const sourceY = this.height - 1 - y;
        gl.readPixels(x, sourceY, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, pixelData);

        // 6. 清理所有临时对象，恢复默认状态
        gl.bindFramebuffer(gl.FRAMEBUFFER, null);
        gl.deleteFramebuffer(tempFbo);

        // 7. 返回 Alpha 分量
        const alpha = pixelData[3];
        
        // (可选) 保留最终的确认日志
        // console.log(`Read Alpha at ${x},${y} (flipped to ${sourceY}) = ${alpha}`);
        
        return alpha;
    }
    // --- 修改结束 ---

    invalidateAllPlayersPhysics() {
        for (let player of this.playerList) {
            player.invalidatePhysics();
        }
    }

    registerPlayer(player) {
        this.playerList.push(player);
        this.invalidateAnimation();
    }

    unregisterPlayer(player) {
        this.playerList.splice(this.playerList.indexOf(player), 1);
        this.checkCanvasHide(player.canvas);
        this.invalidateAnimation();
    }

    invalidateAnimation() {
        for (let i = 0; i < this.playerList.length; i++)
            this.playerList[i].index = i;
        this.playerList.sort( (a, b) => {
            if (a.canvas.id == null
                && b.canvas.id != null)
                return -1;
            if (a.canvas.id != null
                && b.canvas.id == null)
                return 1;
            if (a.canvas.id < b.canvas.id)
                return -1;
            if (a.canvas.id > b.canvas.id)
                return 1;
            if (a.zIndex < b.zIndex)
                return -1;
            if (a.zIndex > b.zIndex)
                return 1;
            return a.index - b.index;
        });
        this.kickAnimation();
    }

    checkAnimationRequired() {
        return this.playerList.length > 0;
    }

    checkCanvasHide(canvas) {
        if (canvas == null)
            return;
        if (! this.playerList.some(player => player.canvas == canvas)) {
            const ctx = canvas.getContext("2d");
            ctx.clearRect(0, 0, canvas.width, canvas.height);
        }
    }

    kickAnimation() {
        if (this.animating
            && ! this.checkAnimationRequired()) {
            this.animating = false;
            cancelAnimationFrame(this.requestId);
        }
        else if (! this.animating
                 && this.checkAnimationRequired()) {
            this.animating = true;
            this.lastAnimationTime = null;
            this.requestId = requestAnimationFrame(this.drawAnimation.bind(this));
        }                
    }

    drawAnimation(timeStamp) {
        if (this.lastAnimationTime === null)
            this.lastAnimationTime = timeStamp;

        const curAnimationTime = timeStamp;
        const diffTime = Math.min(100, (curAnimationTime - this.lastAnimationTime));
        const frameCount = diffTime * EmotePlayer.MS2FRAME;
        this.lastAnimationTime = curAnimationTime;

        const gl = this.gl;
        let canvas = null;

        const beginScene = () => {
            if (canvas == null)
                return;
            gl.clearColor(0.0, 0.0, 0.0, 0.0);
            gl.clear(gl.COLOR_BUFFER_BIT);
        }

        const endScene = (canvas) => {
            if (canvas == null)
                return;
            let ctx = canvas.getContext("2d");
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.drawImage(this.renderCanvas, 
                          (canvas.width - this.width) / 2,
                          (canvas.height - this.height) / 2);
        }

        EmoteDevice_SetMaskMode(EmotePlayer.maskMode);
        EmoteDevice_SetProtectTranslucentTextureColor(EmotePlayer.protectTranslucentTextureColor);
        EmoteDevice_SetMaskRegionClipping(EmotePlayer.maskRegionClipping);

        for (let player of this.playerList) {
            if (player.canvas !== canvas) {
                endScene(canvas);
                canvas = player.canvas;
                beginScene(canvas);
            }

            player.onUpdate();
            if (! player.stepUpdate
                && player.convolveCanvasMovementToPhysics) {
                const curCanvasPosition = player.canvasPosition;
                const prevCanvasPosition = player.prevCanvasPosition;
                const scale = player.getState("scale");
                const vec = [ (curCanvasPosition.left - prevCanvasPosition.left) / scale * frameCount,
                              (curCanvasPosition.top - prevCanvasPosition.top) / scale * frameCount ];
                EmotePlayer_SetOuterForce(player.playerId, "bust", vec[0], vec[1], 0, 0);
                EmotePlayer_SetOuterForce(player.playerId, "parts", vec[0], vec[1], 0, 0);
                EmotePlayer_SetOuterForce(player.playerId, "hair", vec[0], vec[1], 0, 0);
            }
            player.prevCanvasPosition = player.canvasPosition;
            if (player.stepUpdate) {
                if (player.modified) {
                    EmotePlayer_Step(player.playerId);
                    EmotePlayer_Update(player.playerId, 0);
                }
            } else {
                EmotePlayer_Update(player.playerId, frameCount * player.speed);
            }
            player.modified = false;

            if (player.canvas == null
                || player.hide
                || player.globalAlpha == 0)
                continue;

            EmotePlayer_DrawToTexture2(player.playerId, this.renderTexture);
                
            gl.useProgram(this.shader_program);

            // 頂点バッファの登録
            gl.bindBuffer(gl.ARRAY_BUFFER, this.vertexPositionBuffer);
            gl.vertexAttribPointer(this.aLoc[0], 3, gl.FLOAT, false, 0, 0);
            gl.bindBuffer(gl.ARRAY_BUFFER, this.coordBuffer);
            gl.vertexAttribPointer(this.aLoc[1], 2, gl.FLOAT, false, 0, 0);
            
            // uniform値の登録
            gl.uniform2f(this.uLoc[0], this.width, this.height);
            gl.uniform2f(this.uLoc[1], this.width, this.height);
            gl.uniformMatrix4fv(this.uLoc[2], false, this.pMatrix);
            gl.uniform1i(this.uLoc[3], 0);
            gl.uniform4f(this.uLoc[4], 
                         EmotePlayer_GetVariable(player.playerId, "_globalR") / 255,
                         EmotePlayer_GetVariable(player.playerId, "_globalG") / 255,
                         EmotePlayer_GetVariable(player.playerId, "_globalB") / 255,
                         EmotePlayer_GetVariable(player.playerId, "_globalA") / 255);

            gl.activeTexture(gl.TEXTURE0);
            var tex = EmoteDevice_GetEmoteTexture2Tex(this.renderTexture);
            gl.bindTexture(gl.TEXTURE_2D, tex);
            
            gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
            gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
            
            gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
            gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);

            gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, this.vertexIndexBuffer);

            gl.blendEquation(gl.FUNC_ADD);
            gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
            gl.enable(gl.BLEND);

            gl.drawElements(gl.TRIANGLES, 6, gl.UNSIGNED_SHORT, 0);
        }

        endScene(canvas);
        
        this.requestId = requestAnimationFrame(this.drawAnimation.bind(this));
    }
};

class EmotePlayer
{
    constructor(canvas = null) {
        this._canvas = canvas;
        this.playerId = null;
        this.initialized = false;
        this.initMembers();
        EmotePlayer.requireDevice();
    }

    destroy() {
        unloadData();
        EmotePlayer.releaseDevice();
    }

    initMembers() {
        this.initialized = false;
        this.registered = false;
        this.isCharaProfileAvailable = false;
        this.charaHeight = 0;
        this.charaProfile = {};
        this.charaBounds = {};
        this._meshDivisionRatio = 1;
        this._hairScale = 1;
        this._partsScale = 1;
        this._bustScale = 1;
        this._speed = 1;
        this._windSpeed = 0;
        this._windPowMin = 0;
        this._windPowMax = 2;
        this._coord = [ 0, 0 ];
        this._scale = 1;
        this._rot = 0;
        this._vertexR = this._vertexG = this._vertexB = 128;
        this._globalR = this._globalG = this._globalB = this._globalA = 255;
        this._grayscale = 0.0;
        this._zIndex = 0;
        this._hide = false;
        this._stepUpdate = false;
        this.modified = true;
        this._convolveCanvasMovementToPhysics = false;
        this.prevCanvasPosition = { left: 0, top: 0 };
        this._variableList = [];
        this._variableListLoaded = false;
        this._mainTimelineLabel = "";
        this._mainTimelineLabels = [];
        this._mainTimelineLabelsLoaded = false;
        this._diffTimelineSlot = [ "", "", "", "", "", "" ];
        this._diffTimelineFadeOutTime = 300;
        this._diffTimelineLabels = [];
        this._diffTimelineLabelsLoaded = false;

        // --- 修改开始 ---
        // 为事件系统初始化一个容器
        this._eventListeners = {
            'transformchange': [] // 预定义我们需要的 'transformchange' 事件
        };
        // --- 修改结束 ---
    }

    // --- 修改开始 ---
    // 新增：事件订阅 (on) 和发布 (emit) 方法

    /**
     * 订阅一个事件。
     * @param {string} eventName - 事件名称 (e.g., 'transformchange')。
     * @param {function} callback - 事件触发时要调用的函数。
     */
    on(eventName, callback) {
        if (this._eventListeners[eventName]) {
            this._eventListeners[eventName].push(callback);
        } else {
            console.warn(`Attempted to subscribe to an unknown event: ${eventName}`);
        }
    }

    /**
     * 取消订阅一个事件。
     * @param {string} eventName - 事件名称。
     * @param {function} callback - 要移除的回调函数。
     */
    off(eventName, callback) {
        if (this._eventListeners[eventName]) {
            this._eventListeners[eventName] = this._eventListeners[eventName].filter(
                listener => listener !== callback
            );
        }
    }

    /**
     * 发布一个事件，通知所有订阅者。
     * @param {string} eventName - 事件名称。
     * @param {object} data - (可选) 传递给回调函数的数据。
     */
    emit(eventName, data) {
        if (this._eventListeners[eventName]) {
            this._eventListeners[eventName].forEach(callback => {
                try {
                    callback(data);
                } catch (e) {
                    console.error(`Error in event listener for '${eventName}':`, e);
                }
            });
        }
    }

    // --- 修改结束 ---

    get needsDrawing() {
        return this.initialized;
    }

    invalidateDrawing() {
        const needs = this.needsDrawing;
        if (this.registered != needs) {
            if (needs) {
                EmotePlayer.device.registerPlayer(this);
                this.onRegister();
            } else {
                this.onUnregsiter();
                EmotePlayer.device.unregisterPlayer(this);
            }
            this.registered = needs;
        }
    }

    get meshDivisionRatio() {
        return this._meshDivisionRatio;
    }
    set meshDivisionRatio(val) {
        if (this._meshDivisionRatio == val)
            return;
        this._meshDivisionRatio = val;
    }

    get hairScale() {
        return this._hairScale;
    }
    set hairScale(val) {
        if (this._hairScale == val)
            return;
        this._hairScale = val;
        this.invalidatePhysics();
    }

    get partsScale() {
        return this._partsScale;
    }
    set partsScale(val) {
        if (this._partsScale == val)
            return;
        this._partsScale = val;
        this.invalidatePhysics();
    }

    get bustScale() {
        return this._bustScale;
    }
    set bustScale(val) {
        if (this._bustScale == val)
            return;
        this._bustScale = val;
        this.invalidatePhysics();
    }

    invalidatePhysics() {
        if (! this.initialized)
            return;
        EmotePlayer_SetHairScale (this.playerId, this.hairScale  * EmotePlayer.globalHairScale );
        EmotePlayer_SetPartsScale(this.playerId, this.partsScale * EmotePlayer.globalPartsScale);
        EmotePlayer_SetBustScale (this.playerId, this.bustScale  * EmotePlayer.globalBustScale );
    }

    get windSpeed() {
        return this._windSpeed;
    }
    set windSpeed(val) {
        if (this._windSpeed == val)
            return;
        this._windSpeed = val;
        this.invalidateWind();
    }

    get windPowMin() {
        return this._windPowMin;
    }
    set windPowMin(val) {
        if (this._windPowMin == val)
            return;
        this._windPowMin = val;
        this.invalidateWind();
    }

    get windPowMax() {
        return this._windPowMax;
    }
    set windPowMax(val) {
        if (this._windPowMax == val)
            return;
        this._windPowMax = val;
        this.invalidateWind();
    }

    invalidateWind() {
        if (! this.initialized)
            return;
        if (this._windSpeed == 0) {
            EmotePlayer_StopWind(this.playerId);
        } else {
            const w = EmotePlayer.device.width / 2;
            EmotePlayer_StartWind(this.playerId, -w, w, this._windSpeed, this._windPowMin, this._windPowMax);
        }
    }
    get zIndex() {
        return this._zIndex;
    }
    set zIndex(val) {
        this._zIndex = val;
        EmotePlayer.device.invalidateAnimation();
    }

    get hide() {
        return this._hide;
    }
    set hide(val) {
        if (this._hide == val)
            return;
        this._hide = val;
    }       

    get canvas() {
        return this._canvas;
    }
    set canvas(val) {
        if (this._canvas === val)
            return;
        const prevCanvas = this._canvas;
        this._canvas = val;
        EmotePlayer.device.checkCanvasHide(prevCanvas);
        EmotePlayer.device.invalidateAnimation();
        this.prevCanvasPosition = this.canvasPosition;
    }

    colorStrToValue(str) {
        if (str.substr(0, 1) == '#')
            str = str.substr(1);
        return { r: parseInt(str.substr(0, 2), 16),
                 g: parseInt(str.substr(2, 2), 16),
                 b: parseInt(str.substr(4, 2), 16) };
    }

    colorValueToStr(r, g, b) {
        const toHex = (val) => ('0' + val.toString(16).toUpperCase()).substr(-2);
        return '#' + toHex(r) + toHex(g) + toHex(b);
    }

    getBinaryAsync(url) {
        return new Promise( (resolve, reject) => {
            const xhr = new XMLHttpRequest();
            xhr.open("GET", url, true);
            xhr.responseType = "arraybuffer";
            xhr.onload = () => {
                if (xhr.status === 200)
                    resolve(new Uint8Array(xhr.response));
                else
                    reject(new Error(xhr.statusText));
            }
            xhr.onerror = () => reject(new Error(xhr.statusText));
            xhr.send();
        });
    }

    promiseLoadDataFromURL(...urls) {
        urls = Array.prototype.concat.apply([], urls);
        const tasks = urls.map(url => this.getBinaryAsync(url));
        return Promise.all(tasks)
        .then(this.loadData.bind(this))
    }

    loadDataFromURL(...urls) {
        this.promiseLoadDataFromURL(...urls)
        .catch(error => console.error(error));
    }

    unloadData() {
        if (! this.initialized)
            return;
        EmotePlayer_Finish(this.playerId);
        this.playerId = null;
        this.initialized = false;
        this.clearVariableList();
        this.clearMainTimelineLabels();
        this.clearDiffTimelineLabels();
        this.clearCharaProfile();
        this.invalidateDrawing();
    }

    loadData(...files) {
        files = Array.prototype.concat.apply([], files);
        this.unloadData();
        this.playerId = EmotePlayer_Initialize(files);
        this.initialized = true;
        this.modified = true;
        this.loadCharaProfile();
        EmotePlayer_SetMeshDivisionRatio(this.playerId, this.meshDivisionRatio * EmotePlayer.globalMeshDivisionRatio);
        EmotePlayer_SetCoord(this.playerId, this._coord[0], this._coord[1], 0, 0);
        EmotePlayer_SetScale(this.playerId, this._scale, 0, 0);
        EmotePlayer_SetRot(this.playerId, this._rot, 0, 0);
        EmotePlayer_SetVariable(this.playerId, "_globalR", this._globalR, 0, 0);
        EmotePlayer_SetVariable(this.playerId, "_globalG", this._globalG, 0, 0);
        EmotePlayer_SetVariable(this.playerId, "_globalB", this._globalB, 0, 0);
        EmotePlayer_SetVariable(this.playerId, "_globalA", this._globalA, 0, 0);
        EmotePlayer_SetGrayscale(this.playerId, this._grayscale, 0, 0);
        EmotePlayer_SetColor(this.playerId, this._vertexR/255, this._vertexG/255, this._vertexB/255, 1, 0, 0);
        this.invalidateWind();
        this.invalidatePhysics();
        if (this._mainTimelineLabel != "") 
			EmotePlayer_PlayTimeline(this.playerId, this._mainTimelineLabel, EmotePlayer.TimelinePlayFlags.PARALLEL);
        for (let val of this._diffTimelineSlot) 
            if (val != "")
				EmotePlayer_PlayTimeline(this.playerId, val, 
                                         EmotePlayer.TimelinePlayFlags.PARALLEL | EmotePlayer.TimelinePlayFlags.DIFFERENCE);
        this.prevCanvasPosition = this.canvasPosition;
        this.invalidateDrawing();
    }

    loadCharaProfile() {
        this.isCharaProfileAvailable = EmotePlayer_IsCharaProfileAvailable(this.playerId);
        if (this.isCharaProfileAvailable) {
            this.charaHeight = EmotePlayer_GetCharaHeight(this.playerId);
            this.charaProfile = {};
            const charaProflleCount = EmotePlayer_CountCharaProfiles(this.playerId);
            for (let i = 0; i < charaProflleCount; i++) {
                const s = EmotePlayer_GetCharaProfileLabelAt(this.playerId, i);
                const value = EmotePlayer_GetCharaProfile(this.playerId, s);
                this.charaProfile[s] = value;
            }
            this.charaBounds = { left: this.charaProfile.boundsLeft,
                                 top: this.charaProfile.boundsTop,
                                 right: this.charaProfile.boundsRight,
                                 bottom: this.charaProfile.boundsBottom };
            delete this.charaProfile.boundsLeft;
            delete this.charaProfile.boundsTop;
            delete this.charaProfile.boundsRight;
            delete this.charaProfile.boundsBottom;
        }
    }

    clearCharaProfile() {
        this.isCharaProfileAvailable = false;
        this.charaHeight = 0;
        this.charaProfile = {};
        this.charaBounds = {};
    }

    getState(label) {
        if (! this.initialized)
            return 0;
        return EmotePlayer_GetState(this.playerId, label);
    }

    getMarkerPosition(marker) {
        if (! this.initialized
            || this.canvas == null)
            return null;

        let markerCoord = [ 0, 0 ];
        if (marker in this.charaProfile) {
            const _x = this.getState("coordX");
            const _y = this.getState("coordY");
            const _scale = this.getState("scale");
            const _rot = this.getState("rot");
            const s = Math.sin(_rot);
            const c = Math.cos(_rot);
            const markerX = 0;
            const markerY = this.charaProfile[marker];
            markerCoord = [ markerX * c * _scale + markerY * -s * _scale + _x,
                            markerX * s * _scale + markerY *  c * _scale + _y ];
        }
        const w = this.canvas.width / 2;
        const h = this.canvas.height / 2;
        const rect = this.canvas.getBoundingClientRect();
        return { x: markerCoord[0],
                 y: markerCoord[1],
                 offsetX: markerCoord[0] + w,
                 offsetY: markerCoord[1] + h,
                 clientX: markerCoord[0] + w + rect.left,
                 clientY: markerCoord[1] + h + rect.top };
    }

    get speed() {
        return this._speed;
    }
    set speed(val) {
        this._speed = val;
    }

    get coord() {
        return [].concat(this._coord);
    }
    set coord(val) {
        this.setCoord(val[0], val[1]);
    }
    get scale() {
        return this._scale;
    }
    set scale(val) {
        this.setScale(val);
    }
    get rot() {
        return this._rot;
    }
    set rot(val) {
        this.setRot(val);
    }

    get vertexColor() {
        return this.colorValueToStr(this._vertexR, this._vertexG, this._vertexB);
    }
    set vertexColor(val) {
        this.setVertexColor(val);
    }

    get globalColor() {
        return this.colorValueToStr(this._globalR, this._globalG, this._globalB);
    }
    set globalColor(val) {
        this.setGlobalColor(val);
    }
    get globalAlpha() {
        return this._a / 255;
    }
    set globalAlpha(val) {
        this.setGlobalAlpha(val);
    }
    get grayscale() {
        return this._grayscale;
    }
    set grayscale(val) {
        this.setGrayscale(val);
    }

    setCoord(x, y, ms = 0, easing = 0) {
        if (this._coord[0] == x 
            && this._coord[1] == y)
            return;
        this._coord[0] = x;
        this._coord[1] = y;
        if (this.initialized) {
            this.modified = true;
            EmotePlayer_SetCoord(this.playerId, x, y, ms * EmotePlayer.MS2FRAME, easing);

            // --- 修改开始 ---
            this.emit('transformchange');
            // --- 修改结束 ---
        }
    }

    setScale(scale, ms = 0, easing = 0) {
        if (this._scale == scale)
            return;
        this._scale = scale;
        if (this.initialized) {
            this.modified = true;
            EmotePlayer_SetScale(this.playerId, scale, ms * EmotePlayer.MS2FRAME, easing);

            // --- 修改开始 ---
            this.emit('transformchange');
            // --- 修改结束 ---
        }
    }

    setRot(rot, ms = 0, easing = 0) {
        if (this._rot == rot)
            return;
        this._rot = rot;
        if (this.initialized) {
            this.modified = true;
            EmotePlayer_SetRot(this.playerId, rot, ms * EmotePlayer.MS2FRAME, easing);

            // --- 修改开始 ---
            this.emit('transformchange');
            // --- 修改结束 ---
        }
    }

    setVertexColor(color, ms = 0, easing = 0) {
        color = this.colorStrToValue(color);
        if (this._vertexR == color.r
            && this._vertexG == color.g
            && this._vertexB == color.b)
            return;
        this._vertexR = color.r;
        this._vertexG = color.g;
        this._vertexB = color.b;
        if (this.initialized) {
            this.modified = true;
            EmotePlayer_SetColor(this.playerId, color.r/255, color.g/255, color.b/255, 1, ms * EmotePlayer.MS2FRAME, easing);
        }
    }

    setGlobalColor(color, ms = 0, easing = 0) {
        color = this.colorStrToValue(color);
        if (this._globalR == color.r
            && this._globalG == color.g
            && this._globalB == color.b)
            return;
        this._globalR = color.r;
        this._globalG = color.g;
        this._globalB = color.b;
        if (this.initialized) {
            this.modified = true;
            EmotePlayer_SetVariable(this.playerId, "_globalR", color.r, ms * EmotePlayer.MS2FRAME, easing);
            EmotePlayer_SetVariable(this.playerId, "_globalG", color.g, ms * EmotePlayer.MS2FRAME, easing);
            EmotePlayer_SetVariable(this.playerId, "_globalB", color.b, ms * EmotePlayer.MS2FRAME, easing);
        }
    }

    setGlobalAlpha(alpha, ms = 0, easing = 0) {
        alpha *= 255;
        if (this._globalA == alpha)
            return;
        this._globalA = alpha;
        if (this.initialized) {
            this.modified = true;
            EmotePlayer_SetVariable(this.playerId, "_globalA", alpha, ms * EmotePlayer.MS2FRAME, easing);
        }
    }

    setGrayscale(grayscale, ms = 0, easing = 0) {
        if (this._grayscale == grayscale)
            return;
        this._grayscale = grayscale;
        if (this.initialized) {
            this.modified = true;
            EmotePlayer_SetGrayscale(this.playerId, this._grayscale, ms * EmotePlayer.MS2FRAME, easing);
        }
    }

    get canvasPosition() {
        if (this.canvas == null)
            return this.prevCanvasPosition;
        else {
            const rect = this.canvas.getBoundingClientRect();
            return { left: rect.left + window.scrollX, top: rect.top + window.scrollY };
        }
    }

    get convolveCanvasMovementToPhysics() {
        return this._convolveCanvasMovementToPhysics;
    }
    set convolveCanvasMovementToPhysics(val) {
        if (val == this._convolveCanvasMovementToPhysics)
            return;
        this._convolveCanvasMovementToPhysics = val;
        if (this.initialized
            && ! val) {
            EmotePlayer_SetOuterForce(this.playerId, "bust", 0, 0, 0, 0);
            EmotePlayer_SetOuterForce(this.playerId, "parts", 0, 0, 0, 0);
            EmotePlayer_SetOuterForce(this.playerId, "hair", 0, 0, 0, 0);
        }
    }

    isLoopTimeline(label) {
        if (! this.initialized)
            return false;
        return EmotePlayer_IsLoopTimeline(this.playerId, label);
    }

    getTimelineTotalMilliSeconds(label) {
        if (! this.initialized)
            return false;
        return EmotePlayer_GetTimelineTotalFrameCount(this.playerId, label) * EmotePlayer.FRAME2MS;
    }

    playTimeline(label, flags = 0) {
        if (! this.initialized)
            return;
        this.modified = true;
        EmotePlayer_PlayTimeline(this.playerId, label, flags);
    }

    stopTimeline(label = "") {
        if (! this.initialized)
            return;
        this.modified = true;
        EmotePlayer_StopTimeline(this.playerId, label);
    }

    isTimelinePlaying(label = "") {
        if (! this.initialized)
            return false;
        return EmotePlayer_IsTimelinePlaying(this.playerId, label);
    }

    setTimelineBlendRatio(label, value, ms = 0, easing = 0, stopWhenBlendDone = false) {
        if (! this.initialized)
            return;
        this.modified = true;
        EmotePlayer_SetTimelineBlendRatio(this.playerId, label, value, ms * EmotePlayer.MS2FRAME, easing, stopWhenBlendDone);
    }

    getTimelineBlendRatio(label) {
        if (! this.initialized)
            return 0;
        return EmotePlayer_GetTimelineTotalFrameCount(this.playerId, label);
    }

    fadeInTimeline(label, ms, easing = 0) {
        if (! this.initialized)
            return;
        this.modified = true;
        EmotePlayer_FadeInTimeline(this.playerId, label, ms * EmotePlayer.MS2FRAME, easing);
    }


    fadeOutTimeline(label, ms, easing = 0) {
        if (! this.initialized)
            return;
        this.modified = true;
        EmotePlayer_FadeOutTimeline(this.playerId, label, ms * EmotePlayer.MS2FRAME, easing);
    }

    clearVariableList() {
        this._variableList = [];
        this._variableListLoaded = false;
    }

    touchVariableList() {
        if (this._variableListLoaded
            || ! this.initialized)
            return;
        const variableCount = EmotePlayer_CountVariables(this.playerId);
        for (let i = 0; i < variableCount; i++) {
            const variable = { label: "", frameList: [], minValue:  Number.MAX_VALUE, maxValue: Number.MIN_VALUE };
            variable.label = EmotePlayer_GetVariableLabelAt(this.playerId, i);
            const frameCount = EmotePlayer_CountVariableFrameAt(this.playerId, i);
            if (frameCount == 0) 
                continue;
            for (let j = 0; j < frameCount; j++) {
                const frame = { label: "", value: 0 };
                frame.label = EmotePlayer_GetVariableFrameLabelAt(this.playerId, i, j);
                frame.value = EmotePlayer_GetVariableFrameValueAt(this.playerId, i, j);
                variable.minValue = Math.min(variable.minValue, frame.value);
                variable.maxValue = Math.max(variable.maxValue, frame.value);
                variable.frameList.push(frame);
            }
            this._variableList.push(variable);
        }
        this._variableListLoaded = true;
    }

    get variableList() {
        this.touchVariableList();
        return this._variableList;
    }

    clearMainTimelineLabels() {
        this._mainTimelineLabels = [];
        this._mainTimelineLabelsLoaded = false;
    }

    touchMainTimelineLabels() {
        if (this._mainTimelineLabelsLoaded
            || ! this.initialized)
            return;
        const timelineCount = EmotePlayer_CountMainTimelines(this.playerId);
        if (timelineCount > 0) {
            for (let i = 0; i < timelineCount; i++) 
                this._mainTimelineLabels.push(EmotePlayer_GetMainTimelineLabelAt(this.playerId, i));
        }
        this._mainTimelineLabelsLoaded = true;
    }

    get mainTimelineLabels() {
        this.touchMainTimelineLabels();
        return this._mainTimelineLabels;
    }

    set mainTimelineLabel(val) {
        if (this._mainTimelineLabel == val) {
            return;
        }
        if (! this.initialized) {
            this._mainTimelineLabel = val;
            return;
        }
        if (this._mainTimelineLabel != "") 
			EmotePlayer_StopTimeline(this.playerId, this._mainTimelineLabel);
        this._mainTimelineLabel = val;
        if (this._mainTimelineLabel != "") 
			EmotePlayer_PlayTimeline(this.playerId, this._mainTimelineLabel, EmotePlayer.TimelinePlayFlags.PARALLEL);
        this.modified = true;
    }

    get mainTimelineLabel() {
        return this._mainTimelineLabel;
    }

    clearDiffTimelineLabels() {
        this._diffTimelineLabels = [];
        this._diffTimelineLabelsLoaded = false;
    }

    touchDiffTimelineLabels() {
        if (this._diffTimelineLabelsLoaded
            || ! this.initialized)
            return;
        const timelineCount = EmotePlayer_CountDiffTimelines(this.playerId);
        if (timelineCount > 0) {
            for (let i = 0; i < timelineCount; i++) 
                this._diffTimelineLabels.push(EmotePlayer_GetDiffTimelineLabelAt(this.playerId, i));
        }
        this._diffTimelineLabelsLoaded = true;
    }

    get diffTimelineLabels() {
        this.touchDiffTimelineLabels();
        return this._diffTimelineLabels;
    }

    set diffTimelineFadeoutTime(val) {
        this._diffTimelineFadeOutTime = val;
    }

    get diffTimelineFadeoutTime() {
        return this._diffTimelineFadeOutTime;
    }

    set diffTimelineSlot1(val) {
        this.setDiffTimelineLabel(0, val, this._diffTimelineFadeOutTime);
    }
    get diffTimelineSlot1() {
        return this.getDiffTimelineLabel(0);
    }

    set diffTimelineSlot2(val) {
        this.setDiffTimelineLabel(1, val, this._diffTimelineFadeOutTime);
    }
    get diffTimelineSlot2() {
        return this.getDiffTimelineLabel(1);
    }

    set diffTimelineSlot3(val) {
        this.setDiffTimelineLabel(2, val, this._diffTimelineFadeOutTime);
    }
    get diffTimelineSlot3() {
        return this.getDiffTimelineLabel(2);
    }

    set diffTimelineSlot4(val) {
        this.setDiffTimelineLabel(3, val, this._diffTimelineFadeOutTime);
    }
    get diffTimelineSlot4() {
        return this.getDiffTimelineLabel(3);
    }

    set diffTimelineSlot5(val) {
        this.setDiffTimelineLabel(4, val, this._diffTimelineFadeOutTime);
    }
    get diffTimelineSlot5() {
        return this.getDiffTimelineLabel(4);
    }

    set diffTimelineSlot6(val) {
        this.setDiffTimelineLabel(5, val, this._diffTimelineFadeOutTime);
    }
    get diffTimelineSlot6() {
        return this.getDiffTimelineLabel(5);
    }

    setDiffTimelineLabel(index, val, fadeoutMs) {
        if (this._diffTimelineSlot[index] == val)
            return;
        if (! this.initialized) {
            this._diffTimelineSlot[index] = val;
            return;
        }
        if (this._diffTimelineSlot[index] != "")
            EmotePlayer_FadeOutTimeline(this.playerId, this._diffTimelineSlot[index], fadeoutMs * EmotePlayer.MS2FRAME, 0);
        this._diffTimelineSlot[index] = val;
        if (this._diffTimelineSlot[index] != "")
            EmotePlayer_PlayTimeline(this.playerId, this._diffTimelineSlot[index], 
                                     EmotePlayer.TimelinePlayFlags.PARALLEL | EmotePlayer.TimelinePlayFlags.DIFFERENCE);
        this.modified = true;
    }
    getDiffTimelineLabel(index) {
        this.touchDiffTimelineLabels(); 
        return this._diffTimelineSlot[index];
    }

    get playingTimelineInfoList() {
        const result = [];
        if (! this.initialized)
            return result;
        const count = EmotePlayer_CountPlayingTimelines(this.playerId);
        for (let i = 0; i < count; i++) {
            const info = {
                label: EmotePlayer_GetPlayingTimelineLabelAt(this.playerId, i),
                flags: EmotePlayer_GetPlayingTimelineFlagsAt(this.playerId, i)
            };
            result.push(info);
        }
        return result;
    }

    get animating() {
        if (! this.initialized)
            return false;
        return EmotePlayer_IsAnimating(this.playerId);
    }

    skip() {
        if (this.initialized) {
            EmotePlayer_Skip(this.playerId);
            this.prevCanvasPosition = this.canvasPosition;
        }
    }

    pass() {
        if (this.initialized) {
            EmotePlayer_Pass(this.playerId);
            this.prevCanvasPosition = this.canvasPosition;
        }
    }

    get stepUpdate() {
        return this._stepUpdate;
    }

    set stepUpdate(val) {
        if (this._stepUpdate == val)
            return;
        this._stepUpdate = val;
        this.modified = true;
    }

    setVariable(label, value, ms = 0, easing = 0) {
        if (! this.initialized)
            return;
        this.modified = true;
        EmotePlayer_SetVariable(this.playerId, label, value, ms * EmotePlayer.MS2FRAME, easing);
    }

    getVariable(label) {
        if (! this.initialized)
            return 0;
        return EmotePlayer_GetVariable(this.playerId, label);
    }

    setVariableDiff(module, label, value, ms = 0, easing = 0) {
        if (! this.initialized)
            return;
        this.modified = true;
        EmotePlayer_SetVariableDiff(this.playerId, module, label, value, ms * EmotePlayer.MS2FRAME, easing);
    }

    getVariableDiff(module, label) {
        if (! this.initialized)
            return 0;
        return EmotePlayer_GetVariableDiff(this.playerId, module, label);
    }

    onRegister() {
    }

    onUnregsiter() {
    }

    onUpdate() {
    }
};

EmotePlayer.TimelinePlayFlags = {
	PARALLEL:  1 << 0,
	DIFFERENCE: 1 << 1,
};

EmotePlayer.MaskMode = {
	STENCIL:  0,
	ALPHA: 1,
};
    

EmotePlayer.MS2FRAME = 1 * 60 / 1000;
EmotePlayer.FRAME2MS = 1 * 1000 / 60;
EmotePlayer.deviceRefCount = 0;
EmotePlayer.device = null;
EmotePlayer.renderCanvas = null;
EmotePlayer.maskMode = EmotePlayer.MaskMode.ALPHA;
EmotePlayer.protectTranslucentTextureColor = true;
EmotePlayer.maskRegionClipping = true;
EmotePlayer.globalMeshDivisionRatio = 1.0;

for (label of [ 'hairScale', 'partsScale', 'bustScale' ]) {
    const propLabel = 'global' + label.charAt(0).toUpperCase() + label.slice(1);
    const varLabel = `_${propLabel}`;
    EmotePlayer[varLabel] = 1;
    EmotePlayer.__defineGetter__(propLabel, () => EmotePlayer[varLabel]);
    EmotePlayer.__defineSetter__(propLabel, (val) => {
        if (EmotePlayer[varLabel] == val)
            return;
        EmotePlayer[varLabel] = val;
        if (EmotePlayer.device)
            EmotePlayer.device.invalidateAllPlayersPhysics();
    });
}

EmotePlayer.setRenderCanvas = (canvas) => {
    EmotePlayer.renderCanvas = canvas;
};

EmotePlayer.createRenderCanvas = (width, height) => {
    const body = document.getElementsByTagName("body")[0];
    if (body == null)
        alert("can't state body element on DOM.");

    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    canvas.style.display = "none";
    canvas.style.backgroundColor = "transparent";
    canvas.style.position = "absolute";

    body.appendChild(canvas);

    EmotePlayer.renderCanvas = canvas;
}

EmotePlayer.requireDevice = () => {
    if (EmotePlayer.deviceRefCount++ <= 0)
        EmotePlayer.device = new EmoteDevice();
};

EmotePlayer.releaseDevice = () => {
    if (--sEmotePlayer.deviceRefCount <= 0) {
        EmotePlayer.device.destroy();
        EmotePlayer.device = null;
    }
};
