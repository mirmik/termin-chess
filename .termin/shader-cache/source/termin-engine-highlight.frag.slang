// Highlight pass — outlines selected entities based on ID buffer.
//
// Per-frame uniform data carries the selection state.
// Textures are sampled from the color and ID passes.

import termin_prelude;

[[TerminScope("transient")]]
Sampler2D u_color;

[[TerminScope("transient")]]
Sampler2D u_id;

struct HighlightPushData {
    float3 selected_color;
    float enabled;
    float3 outline_color;
    float _pad0;
    float2 texel_size;
};

[[TerminScope("draw")]]
ConstantBuffer<HighlightPushData> u_params;

struct FragmentInput {
    float2 uv : TEXCOORD0;
};

struct FragmentOutput {
    float4 color : SV_Target0;
};

float is_selected(float3 id_color) {
    float d = distance(id_color, u_params.selected_color);
    return float(d < 0.001);
}

[shader("fragment")]
FragmentOutput fs_main(FragmentInput input) {
    float4 base = u_color.Sample(input.uv);

    if (u_params.enabled < 0.5) {
        FragmentOutput output;
        output.color = base;
        return output;
    }

    float3 id_center = u_id.Sample(input.uv).rgb;
    float center_sel = is_selected(id_center);

    float2 ts = u_params.texel_size;
    float neigh_sel = 0.0;
    neigh_sel = max(neigh_sel, is_selected(u_id.Sample(input.uv + float2( ts.x,  0.0)).rgb));
    neigh_sel = max(neigh_sel, is_selected(u_id.Sample(input.uv + float2(-ts.x,  0.0)).rgb));
    neigh_sel = max(neigh_sel, is_selected(u_id.Sample(input.uv + float2( 0.0,  ts.y)).rgb));
    neigh_sel = max(neigh_sel, is_selected(u_id.Sample(input.uv + float2( 0.0, -ts.y)).rgb));

    float outline = 0.0;
    outline = max(outline, center_sel * (1.0 - neigh_sel));
    outline = max(outline, neigh_sel * (1.0 - center_sel));

    FragmentOutput output;
    if (outline > 0.0) {
        float k = 0.8;
        float3 col = lerp(base.rgb, u_params.outline_color, k);
        output.color = float4(col, base.a);
    } else {
        output.color = base;
    }
    return output;
}
