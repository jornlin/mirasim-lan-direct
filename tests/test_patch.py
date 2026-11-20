import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mld import asar, patch  # noqa: E402
from helpers import make_tree  # noqa: E402


TARGETS = [patch.Target("pc-test", "http://10.0.0.5:4939", "token123", "e2e456", "mld-test", True)]


class PatchTests(unittest.TestCase):
    def setUp(self):
        self.a = make_tree()

    def test_patch_js_and_marker(self):
        changed = patch.patch_js(self.a, TARGETS)
        self.assertEqual(changed, ["/dist/renderer/assets/default-space.js"])
        data = self.a.get("/dist/renderer/assets/default-space.js")
        self.assertIn(patch.MARK_PREFIX.encode(), data)
        self.assertIn(b'"pc-test"', data)
        self.assertNotIn(b'ex\te.gatewayUrl??"";return{mode:"remote",host:""', data)
        self.assertEqual(patch.read_marker(self.a), patch.marker_for(TARGETS))

    def test_install_id_pass_through(self):
        patch.patch_js(self.a, TARGETS)
        changed = patch.patch_install_id(self.a)
        self.assertEqual(changed, ["/dist/renderer/assets/default-space.js"])
        js = self.a.get("/dist/renderer/assets/default-space.js").decode()
        self.assertIn("installId:e.installId||void 0", js)
        self.assertIn("member:e.member||void 0", js)
        self.assertIn('"i":"mld-test"', js)

    def test_member_config_flags(self):
        t = patch.Target("pc-test", "http://10.0.0.5:4939", "", "e2e456",
                         "mld-test", True, False, "", True)
        cfg = t.as_config()
        self.assertTrue(cfg.get("c"))
        self.assertTrue(cfg.get("m"))
        self.assertNotIn("g", cfg)

    def test_hybrid_transport(self):
        changed = patch.patch_hybrid_transport(self.a)
        self.assertEqual(changed, ["/dist/renderer/assets/strategy.js"])
        js = self.a.get("/dist/renderer/assets/strategy.js").decode()
        self.assertIn("t.gatewayUrl&&!t.host&&t.nodeId", js)
        self.assertIn("client:HYB(t,e,Ss({host:t.host", js)
        self.assertIn("function HYB(", js)
        self.assertIn("grant:(t.gatewayUrl&&t.host&&!t.member)?void 0:t.grant", js)

    def test_collab_gate(self):
        changed = patch.patch_collab_gate(self.a)
        self.assertEqual(changed, ["/dist/renderer/assets/presence.js"])
        js = self.a.get("/dist/renderer/assets/presence.js").decode()
        self.assertIn("globalThis.__mldCollab===!0", js)

    def test_install_id_route(self):
        changed = patch.patch_install_id_route(self.a)
        self.assertEqual(changed, ["/dist/renderer/assets/strategy.js"])
        js = self.a.get("/dist/renderer/assets/strategy.js").decode()
        self.assertIn("...t.installId?{installId:t.installId}:{},", js)

    def test_csp_and_idempotency(self):
        changed = patch.patch_csp(self.a, ["http://10.0.0.5:4939"])
        self.assertEqual(changed, ["/dist/renderer/index.html"])
        html = self.a.get("/dist/renderer/index.html").decode()
        self.assertIn("http://10.0.0.5:* ws://10.0.0.5:*", html)
        self.assertIn("frame-src 'self' http://10.0.0.5:*", html)
        before = html
        self.assertEqual(patch.patch_csp(self.a, ["http://10.0.0.5:4939"]), [])
        self.assertEqual(self.a.get("/dist/renderer/index.html").decode(), before)

    def test_patch_requires_exactly_one_function(self):
        self.a.contents["/dist/renderer/assets/other.js"] = self.a.get(
            "/dist/renderer/assets/default-space.js")
        with self.assertRaises(patch.PatchError):
            patch.patch_js(self.a, TARGETS)

    def test_renamed_helpers_are_preserved(self):
        js = (
            b'const RD="wss://rendezvous.example/x";'
            b"function Kh(e){return!!e.grant}"
            b"function Nz(e){return e.v2Cert?{v2Cert:e.v2Cert}:{}}"
            b'function L(e){const t=e.gatewayUrl??"";return{mode:"remote",host:"",token:e.token??"",'
            b"...Kh(e)&&!e.token?{grant:e.grant}:{},...typeof e.grantAt==\"number\"?{grantAt:e.grantAt}:{},"
            b'...t?{gatewayUrl:t}:{},nodeId:e.nodeId,e2e:e.e2e,rendezvous:e.rendezvous||RD,...Nz(e)}}'
        )
        from helpers import FILES
        files = dict(FILES)
        files["dist/renderer/assets/default-space.js"] = js
        a = make_tree(files)
        patch.patch_js(a, TARGETS)
        out = a.get("/dist/renderer/assets/default-space.js")
        self.assertIn(b"Kh(e)", out)
        self.assertIn(b"Nz(e)", out)
        self.assertIn(b"||RD", out)

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_hybrid_post_wrapper_does_not_recurse(self):
        # The renderer wraps client.post() by assigning to it. The composite
        # must capture the original direct post and honour the override, or
        # every non-presence post calls itself until the stack blows.
        hyb = patch.HYB_FN.decode()
        script = (
            "const cap={};const gw={managed:true,posted:[],post(f){this.posted.push(f);return true},"
            "onFrame(cb){cap.gcb=cb},close(){},dispose(){}};"
            "function Dt(){return gw}"
            + hyb
            + "\nconst directPosts=[];"
              "const direct={connected:true,post(f){directPosts.push(f);return true},"
              "onFrame(cb){cap.fcb=cb;return()=>{}},onConnection(cb){cap.ccb=cb;return()=>{}},"
              "close(){},dispose(){}};"
              "const c=HYB({nodeId:'pc',gatewayUrl:'wss://g',host:'http://h'},{},{...direct});"
              "const seen=[];c.onFrame(f=>seen.push(f.type));"
              "cap.gcb({type:'chatOpened'});cap.gcb({type:'state',state:{collab:true}});"
              "cap.fcb({type:'state',state:{collab:true}});cap.fcb({type:'chatOpen'});"
              "const orig=c.post;c.post=f=>orig(f);"
              "c.post({type:'state'});c.post({type:'presenceUpdate'});c.post({type:'chatOpen'});c.post({type:'setWorkspaceMembers'});"
              "console.log(JSON.stringify({managed:c.managed===true,hello:directPosts[0],seen,direct:directPosts.map(f=>f.type),"
              "gw:gw.posted.map(f=>f.type)}));"
        )
        proc = subprocess.run(["node", "-e", script], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout)
        self.assertTrue(out["managed"])
        self.assertEqual(out["seen"], ["chatOpened", "state"])
        self.assertEqual(out["direct"], ["clientHello", "state"])
        self.assertEqual(out["gw"], ["presenceUpdate", "chatOpen", "setWorkspaceMembers"])
        self.assertEqual(out["hello"], {"type": "clientHello", "remoteByChoice": True})

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_direct_collab_client_flags(self):
        # A direct (no gateway) collab client still needs remote posture and
        # the managed layout flag, and must survive the renderer's post wrapper.
        hyb = patch.HYB_FN.decode()
        script = (
            "const cap={};const posts=[];"
            "const direct={connected:true,post(f){posts.push(f);return true},"
            "onFrame(cb){cap.fcb=cb;return()=>{}},onConnection(cb){cap.ccb=cb;return()=>{}},"
            "close(){},dispose(){}};"
            + hyb
            + "\nconst c=HYB({nodeId:'pc',host:'http://h',collab:true},{},{...direct});"
              "const seen=[];c.onFrame(f=>seen.push(f.type));"
              "cap.fcb({type:'chatOpened'});"
              "const orig=c.post;c.post=f=>orig(f);c.post({type:'chatOpen'});"
              "console.log(JSON.stringify({managed:c.managed===true,"
              "hello:posts[0],seen,posts:posts.map(f=>f.type)}));"
        )
        proc = subprocess.run(["node", "-e", script], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout)
        self.assertTrue(out["managed"])
        self.assertEqual(out["hello"], {"type": "clientHello", "remoteByChoice": True})
        self.assertEqual(out["seen"], ["chatOpened"])
        self.assertEqual(out["posts"], ["clientHello", "chatOpen"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_member_grant_target(self):
        # A member grant replaces the shared token and must not be overridden
        # by the cloud entry's gateway grant or gatewayUrl.
        jwt = ("eyJhbGciOiJIUzI1NiJ9."
               "eyJzdWIiOiJ1c3JfdGVzdCIsImF1ZCI6InBjLXRlc3QiLCJleHAiOjk5OTk5OTk5OTl9.sig")
        target = patch.Target("pc-test", "http://10.0.0.5:4939", "", "e2e456",
                              "mld-test", True, False, jwt)
        patch.patch_js(self.a, [target])
        js = self.a.get("/dist/renderer/assets/default-space.js").decode()
        start = js.index("function L(")
        end = js.index("/*mirasim-lan-direct:")
        fn = js[start:end]
        script = (
            'const M="wss://rendezvous.example/x";'
            "function K(e){return !!e.grant}function N(e){return e.v2Cert?{v2Cert:e.v2Cert}:{}}"
            + fn
            + "\nconst t=L({nodeId:'pc-test',gatewayUrl:'wss://relay.example',"
              "grant:'gateway-session',token:'shared-token',e2e:'cloud-e2e'});"
              "console.log(JSON.stringify({host:t.host,token:t.token,grant:t.grant,"
              "gateway:t.gatewayUrl??null,collab:t.collab===true,e2e:t.e2e}));"
        )
        proc = subprocess.run(["node", "-e", script], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout)
        self.assertEqual(out["host"], "http://10.0.0.5:4939")
        self.assertEqual(out["token"], "")
        self.assertEqual(out["grant"], jwt)
        self.assertIsNone(out["gateway"])
        self.assertTrue(out["collab"])
        self.assertEqual(out["e2e"], "e2e456")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_member_uses_cloud_gateway_session(self):
        # Member mode has no stored token/grant: the cloud directory's gateway
        # session becomes the direct grant, and gatewayUrl is removed.
        target = patch.Target("pc-test", "http://10.0.0.5:4939", "", "e2e456",
                              "mld-test", True, False, "", True)
        patch.patch_js(self.a, [target])
        js = self.a.get("/dist/renderer/assets/default-space.js").decode()
        start = js.index("function L(")
        end = js.index("/*mirasim-lan-direct:")
        fn = js[start:end]
        script = (
            'const M="wss://rendezvous.example/x";'
            "function K(e){return !!e.grant}function N(e){return {}}"
            + fn
            + "\nconst t=L({nodeId:'pc-test',gatewayUrl:'wss://relay.example',"
              "grant:'gateway-session',token:'shared-token'});"
              "console.log(JSON.stringify({token:t.token,grant:t.grant,"
              "gateway:t.gatewayUrl??null,collab:t.collab===true,hybrid:t.hybrid===true,member:t.member===true,host:t.host}));"
        )
        proc = subprocess.run(["node", "-e", script], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout)
        self.assertEqual(out["token"], "")
        self.assertEqual(out["grant"], "gateway-session")
        self.assertEqual(out["gateway"], "wss://relay.example")
        self.assertTrue(out["collab"])
        self.assertTrue(out["hybrid"])
        self.assertTrue(out["member"])
        self.assertEqual(out["host"], "http://10.0.0.5:4939")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_patched_function_behaviour(self):
        patch.patch_js(self.a, TARGETS)
        js = self.a.get("/dist/renderer/assets/default-space.js").decode()
        start = js.index("function L(")
        end = js.index("/*mirasim-lan-direct:")
        fn = js[start:end]
        script = (
            'const M="wss://rendezvous.example/x";'
            "function K(e){return !!e.grant}function N(e){return e.v2Cert?{v2Cert:e.v2Cert}:{}}"
            + fn
            + "\nconst t=L({nodeId:'pc-test',gatewayUrl:'wss://relay.example',grant:'G',"
              "grantAt:1,e2e:'',v2Cert:'C'});"
              "const o=L({nodeId:'other',gatewayUrl:'wss://relay.example',grant:'G',"
              "grantAt:1,e2e:'key'});"
              "console.log(JSON.stringify({t:{host:t.host,token:t.token,e2e:t.e2e,installId:t.installId,"
              "collabGlobal:globalThis.__mldCollab===true,"
              "gateway:t.gatewayUrl??null,grant:t.grant??null,v2:t.v2Cert??null},"
              "o:{host:o.host,gateway:o.gatewayUrl,grant:o.grant,token:o.token??null,e2e:o.e2e}}));"
        )
        proc = subprocess.run(["node", "-e", script], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout)
        self.assertEqual(out["t"]["host"], "http://10.0.0.5:4939")
        self.assertEqual(out["t"]["token"], "token123")
        self.assertEqual(out["t"]["e2e"], "e2e456")
        self.assertEqual(out["t"]["installId"], "mld-test")
        self.assertTrue(out["t"].get("collabGlobal"))
        self.assertIsNone(out["t"]["gateway"])
        self.assertIsNone(out["t"]["grant"])
        self.assertEqual(out["t"]["v2"], "C")
        # untouched cloud space keeps the gateway path
        self.assertEqual(out["o"]["host"], "")
        self.assertEqual(out["o"]["gateway"], "wss://relay.example")
        self.assertEqual(out["o"]["grant"], "G")
        self.assertEqual(out["o"]["e2e"], "key")

    def test_full_build_loads(self):
        patch.patch_js(self.a, TARGETS)
        patch.patch_install_id(self.a)
        patch.patch_install_id_route(self.a)
        patch.patch_collab_gate(self.a)
        patch.patch_hybrid_transport(self.a)
        patch.patch_csp(self.a, ["http://10.0.0.5:4939"])
        raw = asar.build(self.a)
        asar.verify_bytes(raw)
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".asar", delete=False) as fh:
            fh.write(raw)
            name = fh.name
        try:
            b = asar.load(name)
        finally:
            Path(name).unlink()
        self.assertEqual(b.contents, self.a.contents)


if __name__ == "__main__":
    unittest.main()