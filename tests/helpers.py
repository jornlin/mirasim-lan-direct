from mld import asar

FILES = {
    "package.json": b'{"name":"fake","version":"9.9.9"}',
    "dist/renderer/index.html": (
        b"<html><head><meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'self'; "
        b"connect-src 'self'; img-src 'self'; media-src 'self'; object-src 'self'; "
        b"frame-src 'self'\"></head><body>x</body></html>"
    ),
    "dist/renderer/assets/default-space.js": (
        b'const M="wss://rendezvous.example/x";'
        b"function K(e){return!!e.grant}"
        b"function N(e){return {}}"
        b'function L(e){const t=e.gatewayUrl??"";return{mode:"remote",host:"",token:e.token??"",'
        b"...K(e)&&!e.token?{grant:e.grant}:{},...typeof e.grantAt==\"number\"?{grantAt:e.grantAt}:{},"
        b'...t?{gatewayUrl:t}:{},nodeId:e.nodeId,e2e:e.e2e,rendezvous:e.rendezvous||M,...N(e)}}'
        b'function $e(e){return e.mode!=="remote"?null:{mode:"remote",host:e.host,token:e.token||void 0,'
        b'rendezvous:e.rendezvous||void 0,nodeId:e.nodeId||void 0,e2e:e.e2e||void 0,'
        b'grant:e.grant||void 0,gatewayUrl:e.gatewayUrl||void 0,...N(e)}}'
    ),
    "dist/renderer/assets/strategy.js": (
        b'function X(t,e){if(t?.mode==="remote"&&t.host){return{kind:"mirachannel",'
        b"client:S({host:t.host,hosts:t.hosts,rendezvous:t.rendezvous,nodeId:t.nodeId,"
        b"token:t.token,grant:t.grant,e2e:t.e2e,WebSocketImpl:e.WebSocketImpl})}}}"
    ),
    "dist/renderer/assets/presence.js": (
        b'function V(e){e.onFrame(A=>{if(A.type==="state"){const j=A.state.collab===!0;'
        b'j&&e.post({type:"presenceUpdate"})}})}'
    ),
}


def make_tree(files=None):
    files = files or FILES
    tree = {"files": {}}
    contents = {}
    entries = []
    for path, data in files.items():
        parts = path.strip("/").split("/")
        node = tree
        for part in parts[:-1]:
            node = node["files"].setdefault(part, {"files": {}})
        node["files"][parts[-1]] = {"size": 0, "offset": "0", "integrity": {}}
        full = "/" + path.strip("/")
        contents[full] = data
        entries.append((full, node["files"][parts[-1]]))
    return asar.Asar(tree, entries, contents)