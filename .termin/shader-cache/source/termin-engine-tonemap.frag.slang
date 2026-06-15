// Tonemap pass — HDR to LDR with ACES / Reinhard.
//

import termin_prelude;

struct TonemapParams {
    float exposure;
    int method;
};

[[TerminScope("draw")]]
ConstantBuffer<TonemapParams> u_params;

[[TerminScope("transient")]]
Sampler2D u_input;

struct FragmentInput {
    float2 uv : TEXCOORD0;
};

struct FragmentOutput {
    float4 color : SV_Target0;
};

float3 aces_tonemap(float3 x) {
    const float a = 2.51;
    const float b = 0.03;
    const float c = 2.43;
    const float d = 0.59;
    const float e = 0.14;
    return clamp((x * (a * x + b)) / (x * (c * x + d) + e), 0.0, 1.0);
}

float3 reinhard_tonemap(float3 x) {
    return x / (x + float3(1.0, 1.0, 1.0));
}

[shader("fragment")]
FragmentOutput fs_main(FragmentInput input) {
    float3 color = u_input.Sample(input.uv).rgb;
    color *= u_params.exposure;
    if (u_params.method == 0) {
        color = aces_tonemap(color);
    } else if (u_params.method == 1) {
        color = reinhard_tonemap(color);
    }

    FragmentOutput output;
    output.color = float4(color, 1.0);
    return output;
}
