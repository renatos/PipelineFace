        for frame_path in frame_paths:
            frame_filename = frame_path.name

            prompt_classify = (
                "Aponte se esta imagem é apenas a pessoa/apresentador ou se é uma tela de computador/slide/texto. "
                "Responda EXATAMENTE uma única palavra: 'ROSTO' (se for apenas o apresentador) ou 'CONTEUDO' (se tiver tela, slides, texto ou busca)."
            )
            classification = self.query_ollama("moondream", prompt_classify, image_path=frame_path).upper()

            is_rosto = ("ROSTO" in classification) and ("CONTEUDO" not in classification)

            if is_rosto:
                console.print(f"  [yellow]🙈 Frame ignorado (apenas rosto): {frame_filename}[/yellow]")
                continue

            target_frames_dir.mkdir(parents=True, exist_ok=True)
            dest = target_frames_dir / frame_filename
            shutil.copy2(frame_path, dest)
            saved_frame_paths.append(str(dest))
