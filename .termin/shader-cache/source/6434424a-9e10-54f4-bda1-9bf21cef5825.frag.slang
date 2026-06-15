import termin_prelude;
struct MaterialParams {
    float4 u_color;
    float u_metallic;
    float u_roughness;
    float u_subsurface;
    float u_diffuse_mul;
    float4 u_emission_color;
    float u_emission_intensity;
    float u_normal_strength;
};
[[TerminScope("material")]]
ConstantBuffer<MaterialParams> material;
[[TerminScope("material")]]
Sampler2D u_albedo_texture;
[[TerminScope("material")]]
Sampler2D u_normal_texture;
[[TerminScope("material")]]
Sampler2D u_metallic_roughness_texture;
[[TerminScope("material")]]
Sampler2D u_occlusion_texture;
[[TerminScope("material")]]
Sampler2D u_emissive_texture;
import termin_lighting;
import termin_shadows;

static const float PI = 3.14159265359;

struct FragmentInput {
    float3 world_pos : TEXCOORD0;
    float3 normal_world : TEXCOORD1;
    float2 uv : TEXCOORD2;
    float3 tangent_world : TEXCOORD3;
    float3 bitangent_world : TEXCOORD4;
    float tbn_valid : TEXCOORD5;
};

struct FragmentOutput {
    float4 color : SV_Target0;
};

float D_GGX(float NdotH, float roughness) {
    float a = roughness * roughness;
    float a2 = a * a;
    float denom = NdotH * NdotH * (a2 - 1.0) + 1.0;
    return a2 / (PI * denom * denom);
}

float G_Smith(float NdotV, float NdotL, float roughness) {
    float r = roughness + 1.0;
    float k = (r * r) / 8.0;
    float G1_V = NdotV / (NdotV * (1.0 - k) + k);
    float G1_L = NdotL / (NdotL * (1.0 - k) + k);
    return G1_V * G1_L;
}

float3 F_Schlick(float cosTheta, float3 F0) {
    return F0 + (1.0 - F0) * pow(clamp(1.0 - cosTheta, 0.0, 1.0), 5.0);
}

float wrap_diffuse(float NdotL, float wrap) {
    return max(0.0, (NdotL + wrap) / (1.0 + wrap));
}

float3 subsurface_color(float3 albedo) {
    return albedo * float3(1.0, 0.4, 0.25);
}

float3 get_normal_from_map(FragmentInput input) {
    float3 normal_sample = u_normal_texture.Sample(input.uv).rgb;
    float3 tangent_normal = normal_sample * 2.0 - 1.0;
    tangent_normal.xy *= material.u_normal_strength;
    tangent_normal = normalize(tangent_normal);

    float3 T = normalize(input.tangent_world);
    float3 B = normalize(input.bitangent_world);
    float3 N = normalize(input.normal_world);
    return normalize(T * tangent_normal.x + B * tangent_normal.y + N * tangent_normal.z);
}

[shader("fragment")]
FragmentOutput main(FragmentInput input) {
    FragmentOutput output;

    float3 N;
    if (input.tbn_valid > 0.001 && material.u_normal_strength > 0.0) {
        N = get_normal_from_map(input);
    } else {
        N = normalize(input.normal_world);
    }

    float3 V = normalize(get_camera_position() - input.world_pos);

    float4 tex_color = u_albedo_texture.Sample(input.uv);
    float3 albedo = material.u_color.rgb * tex_color.rgb;
    float alpha = material.u_color.a * tex_color.a;

    float4 metallic_roughness_sample = u_metallic_roughness_texture.Sample(input.uv);
    float metallic = clamp(material.u_metallic * metallic_roughness_sample.b, 0.0, 1.0);
    float roughness = max(
        clamp(material.u_roughness * metallic_roughness_sample.g, 0.0, 1.0),
        0.04);
    float subsurface = material.u_subsurface;
    float occlusion = u_occlusion_texture.Sample(input.uv).r;

    float3 F0 = lerp(float3(0.04, 0.04, 0.04), albedo, metallic);
    float3 ambient =
        get_ambient_color() * get_ambient_intensity() * albedo *
        (1.0 - metallic * 0.5) * occlusion;

    float3 Lo = float3(0.0, 0.0, 0.0);

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

        float3 H = normalize(V + L);

        float NdotL_raw = dot(N, L);
        float NdotL = max(NdotL_raw, 0.0);
        float NdotV = max(dot(N, V), 0.001);
        float NdotH = max(dot(N, H), 0.0);
        float HdotV = max(dot(H, V), 0.0);

        float D = D_GGX(NdotH, roughness);
        float G = G_Smith(NdotV, NdotL, roughness);
        float3 F = F_Schlick(HdotV, F0);

        float3 numerator = D * G * F;
        float denominator = 4.0 * NdotV * NdotL + 0.0001;
        float3 specular = numerator / denominator;

        float3 kD = (1.0 - F) * (1.0 - metallic);
        float3 diffuse_standard = kD * albedo / PI * material.u_diffuse_mul;

        float wrap_amount = subsurface * 0.5;
        float diffuse_wrap = wrap_diffuse(NdotL_raw, wrap_amount);
        float3 sss_color = subsurface_color(albedo);

        float sss_mask = max(0.0, diffuse_wrap - NdotL) * 2.0;
        float3 diffuse_sss =
            kD * lerp(albedo, sss_color, sss_mask * subsurface) /
            PI * material.u_diffuse_mul;

        float3 diffuse_final =
            lerp(diffuse_standard * NdotL, diffuse_sss * diffuse_wrap, subsurface);

        float shadow = 1.0;
        if (get_light_type(i) == LIGHT_TYPE_DIRECTIONAL) {
            shadow = compute_shadow_auto(i, input.world_pos);
        }

        float3 radiance = get_light_color(i) * get_light_intensity(i) * attenuation;
        Lo += (diffuse_final + specular * NdotL) * radiance * shadow;
    }

    float3 color = ambient + Lo;
    color +=
        u_emissive_texture.Sample(input.uv).rgb *
        material.u_emission_color.rgb *
        material.u_emission_intensity;

    output.color = float4(color, alpha);
    return output;
}
