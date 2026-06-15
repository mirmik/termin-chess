// Bloom composite pass — blends bloom result over the original image.
//

import termin_prelude;

struct BloomCompositeParams {
    float intensity;
};

[[TerminScope("draw")]]
ConstantBuffer<BloomCompositeParams> u_params;

[[TerminScope("transient")]]
Sampler2D u_original;

[[TerminScope("transient")]]
Sampler2D u_bloom;

struct FragmentInput {
    float2 uv : TEXCOORD0;
};

struct FragmentOutput {
    float4 color : SV_Target0;
};

[shader("fragment")]
FragmentOutput fs_main(FragmentInput input) {
    float3 original = u_original.Sample(input.uv).rgb;
    float3 bloom = u_bloom.Sample(input.uv).rgb;
    float3 result = original + bloom * u_params.intensity;

    FragmentOutput output;
    output.color = float4(result, 1.0);
    return output;
}
