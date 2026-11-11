import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Playlists } from './playlists';

describe('Playlists', () => {
  let component: Playlists;
  let fixture: ComponentFixture<Playlists>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Playlists],
    }).compileComponents();

    fixture = TestBed.createComponent(Playlists);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
