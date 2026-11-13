package dev.eqmon.model;

import java.util.List;

/** Contents of {@code models/rul.json}, written by {@code model/export_onnx.py} next to the ONNX file. */
public record ModelMetadata(String version, String arm, int seed, int n_estimators, List<String> feature_names,
        String input_name, String input_type, int cap, int window) {}
