// Solid primitive — flat-colored geometry for editor primitives.
//

import termin_prelude;

struct SolidPush { float4x4 mvp; float4 color; };

[[TerminScope("draw")]]
ConstantBuffer<SolidPush> u_push;

// --- vertex ---
struct VIn  { float3 pos : POSITION; };
struct VOut { float4 pos : SV_Position; };
[shader("vertex")] VOut vs_main(VIn i) { VOut o; o.pos = mul(u_push.mvp, float4(i.pos, 1)); return o; }

// --- fragment ---
struct FOut { float4 color : SV_Target0; };
[shader("fragment")] FOut fs_main() { FOut o; o.color = u_push.color; return o; }
