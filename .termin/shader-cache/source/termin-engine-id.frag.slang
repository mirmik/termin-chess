// ID pass — entity picking shader. Single source for vertex + fragment.
//

import termin_prelude;

struct PerFrame {
    float4x4 view;
    float4x4 projection;
};

struct PushData {
    float4x4 model;
    float4 pick_color;
};

[[TerminScope("frame")]]
ConstantBuffer<PerFrame> u_per_frame;

[[TerminScope("draw")]]
ConstantBuffer<PushData> u_push;

// --- vertex stage ---

struct VertexInput {
    float3 position : POSITION;
    float3 normal   : NORMAL;
    float2 texcoord : TEXCOORD0;
};

struct VertexOutput {
    float4 position : SV_Position;
};

[shader("vertex")]
VertexOutput vs_main(VertexInput input) {
    VertexOutput output;
    output.position = mul(u_per_frame.projection,
                     mul(u_per_frame.view,
                     mul(u_push.model, float4(input.position, 1.0))));
    return output;
}

// --- fragment stage ---

struct FragmentOutput {
    float4 color : SV_Target0;
};

[shader("fragment")]
FragmentOutput fs_main() {
    FragmentOutput output;
    output.color = float4(u_push.pick_color.rgb, 1.0);
    return output;
}
