@program BlinnPhong
@language slang
@features lighting_ubo

// ============================================================
// Blinn-Phong Shader - Canonical Implementation
// ============================================================
//
// Classic Blinn-Phong illumination model:
//   I = Ka*Ia + Kd*Id*(N dot L) + Ks*Is*(N dot H)^n
//
// ============================================================

@phase opaque
@priority 0
@glDepthTest true
@glDepthMask true
@glCull true

@property Color u_diffuse_color = Color(1.0, 1.0, 1.0, 1.0)
@property Color u_specular_color = Color(1.0, 1.0, 1.0, 1.0)
@property Float u_ambient_factor = 1.0 range(0.0, 1.0)
@property Float u_shininess = 32.0 range(1.0, 256.0)
@property Texture2D u_diffuse_texture = "white"

@stage vertex
struct VertexInput {
    float3 position : POSITION;
    float3 normal : NORMAL;
    float2 uv : TEXCOORD0;
};

struct VertexOutput {
    float4 position : SV_Position;
    float3 world_pos : TEXCOORD0;
    float3 normal_world : TEXCOORD1;
    float2 uv : TEXCOORD2;
};

[shader("vertex")]
VertexOutput main(VertexInput input) {
    VertexOutput output;
    float4 world = mul(u_model, float4(input.position, 1.0));
    float3x3 normal_matrix = (float3x3)u_model;

    output.world_pos = world.xyz;
    output.normal_world = normalize(mul(normal_matrix, input.normal));
    output.uv = input.uv;
    output.position = mul(u_projection, mul(u_view, world));
    return output;
}
@endstage

@stage fragment
import termin_lighting;
import termin_shadows;

struct FragmentInput {
    float3 world_pos : TEXCOORD0;
    float3 normal_world : TEXCOORD1;
    float2 uv : TEXCOORD2;
};

struct FragmentOutput {
    float4 color : SV_Target0;
};

[shader("fragment")]
FragmentOutput main(FragmentInput input) {
    FragmentOutput output;

    float3 N = normalize(input.normal_world);
    float3 V = normalize(get_camera_position() - input.world_pos);

    float4 tex_color = u_diffuse_texture.Sample(input.uv);
    float3 Kd = material.u_diffuse_color.rgb * tex_color.rgb;
    float3 Ks = material.u_specular_color.rgb;
    float alpha = material.u_diffuse_color.a * tex_color.a;

    float3 ambient =
        Kd * material.u_ambient_factor * get_ambient_color() * get_ambient_intensity();

    float3 diffuse_sum = float3(0.0, 0.0, 0.0);
    float3 specular_sum = float3(0.0, 0.0, 0.0);

    for (int i = 0; i < get_light_count(); ++i) {
        float3 L;
        float attenuation = 1.0;

        if (get_light_type(i) == LIGHT_TYPE_DIRECTIONAL) {
            L = normalize(-get_light_direction(i));
        } else {
            float3 to_light = get_light_position(i) - input.world_pos;
            float dist = length(to_light);
            L = to_light / max(dist, 0.0001);

            attenuation =
                compute_distance_attenuation(get_light_attenuation(i), get_light_range(i), dist);

            if (get_light_type(i) == LIGHT_TYPE_SPOT) {
                attenuation *= compute_spot_weight(
                    get_light_direction(i),
                    L,
                    get_light_inner_angle(i),
                    get_light_outer_angle(i));
            }
        }

        float shadow = 1.0;
        if (get_light_type(i) == LIGHT_TYPE_DIRECTIONAL) {
            shadow = compute_shadow_auto(i, input.world_pos);
        }

        float3 light_intensity =
            get_light_color(i) * get_light_intensity(i) * attenuation * shadow;

        float NdotL = max(dot(N, L), 0.0);
        diffuse_sum += Kd * light_intensity * NdotL;

        if (NdotL > 0.0) {
            float3 H = normalize(L + V);
            float NdotH = max(dot(N, H), 0.0);
            float specular = pow(NdotH, material.u_shininess);
            specular_sum += Ks * light_intensity * specular;
        }
    }

    output.color = float4(ambient + diffuse_sum + specular_sum, alpha);
    return output;
}
@endstage

@endphase

// ============================================================
// Shadow caster phase
// ============================================================

@phase shadow
@priority 0
@glDepthTest true
@glDepthMask true
@glCull true

@stage vertex
struct ShadowVertexInput {
    float3 position : POSITION;
};

struct ShadowVertexOutput {
    float4 position : SV_Position;
};

[shader("vertex")]
ShadowVertexOutput main(ShadowVertexInput input) {
    ShadowVertexOutput output;
    float4 world = mul(u_model, float4(input.position, 1.0));
    output.position = mul(u_projection, mul(u_view, world));
    return output;
}
@endstage

@stage fragment
struct ShadowFragmentInput {
    float4 position : SV_Position;
};

struct ShadowFragmentOutput {
    float4 color : SV_Target0;
};

[shader("fragment")]
ShadowFragmentOutput main(ShadowFragmentInput input) {
    ShadowFragmentOutput output;
    output.color = float4(input.position.z, 0.0, 0.0, 1.0);
    return output;
}
@endstage

@endphase
