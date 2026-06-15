{{- define "kortes.labels" -}}
app.kubernetes.io/part-of: kortes
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "kortes.image" -}}
{{- .Values.image.registry }}/{{ .repo }}:{{ .Values.image.tag }}
{{- end -}}
