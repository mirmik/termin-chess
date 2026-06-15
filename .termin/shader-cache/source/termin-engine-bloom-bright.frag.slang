// Bloom bright pass — extracts pixels above a luminance threshold.
//
// Pass code reads the assigned numbers from shader layout metadata.

import termin_prelude;

struct BloomBrightParams {
    float threshold;
    float soft_threshold;
};

[[TerminScope("draw")]]
ConstantBuffer<BloomBrightParams> u_params;

[[TerminScope("transient")]]
Sampler2D u_texture;

struct FragmentInput {
    float2 uv : TEXCOORD0;
};

struct FragmentOutput {
    float4 color : SV_Target0;
};

[shader("fragment")]
FragmentOutput fs_main(FragmentInput input) {
    float3 color = u_texture.Sample(input.uv).rgb;
    float brightness = dot(color, float3(0.2126, 0.7152, 0.0722));
    float knee = u_params.threshold * u_params.soft_threshold;
    float soft = brightness - u_params.threshold + knee;
    soft = clamp(soft, 0.0, 2.0 * knee);
    soft = soft * soft / (4.0 * knee + 0.00001);
    float contribution = max(soft, brightness - u_params.threshold) / max(brightness, 0.00001);
    contribution = max(contribution, 0.0);

    FragmentOutput output;
    output.color = float4(color * contribution, 1.0);
    return output;
}
