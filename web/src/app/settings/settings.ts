import { Component, inject, signal, OnInit} from '@angular/core';
import { Router, RouterLink} from '@angular/router';
import { Api } from '../api';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';

@Component({
  imports: [ReactiveFormsModule, RouterLink],
  selector: 'app-settings',
  styleUrl: './settings.scss',
  templateUrl: './settings.html',
})
export class Settings implements OnInit {
  private api = inject(Api);
  private router = inject(Router);
  private fb = inject(FormBuilder);

  form = this.fb.nonNullable.group({
    soulseek_username: '',
    soulseek_password: '',
    music_dir: '',
    share_dir: '',
    credentials_file: '',
    listen_port: 50300,
  });

  status = signal('');
  saving = signal(false);

  ngOnInit() {
    this.api.settings().subscribe(s => this.form.patchValue(s));
  }

  save() {
    this.saving.set(true);
    this.status.set('Setting up...');
    this.api.saveSettings(this.form.getRawValue()).subscribe({
      next: () => this.router.navigateByUrl('/'),
      error: e => { 
        this.saving.set(false); 
        this.status.set(e.error?.detail ?? 'Error'); 
      },
    });
  }
}
